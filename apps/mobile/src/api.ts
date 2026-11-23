import * as SecureStore from "expo-secure-store";
import type { components } from "@smartfit/contracts";
import { apiRequest, ApiError } from "@smartfit/api-client";

const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? "").replace(/\/+$/, "");
const ACCESS_KEY = "smartfit.mobile.access";
const REFRESH_KEY = "smartfit.mobile.refresh";

type User = components["schemas"]["UserOut"];
type Credentials = components["schemas"]["Credentials"];
type OnboardingIn = components["schemas"]["OnboardingIn"];

type SessionResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: User;
};

let refreshInFlight: Promise<string | null> | null = null;

function apiUrl(path: string) {
  if (!API_URL) throw new Error("Configura EXPO_PUBLIC_API_URL en apps/mobile/.env");
  return `${API_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

async function saveSession(access: string, refresh: string) {
  await SecureStore.setItemAsync(ACCESS_KEY, access);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh);
}

export async function clearSession() {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ]);
}

async function refreshSession(): Promise<string | null> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refresh = await SecureStore.getItemAsync(REFRESH_KEY);
    if (!refresh) return null;
    try {
      const response = await fetch(apiUrl("/auth/session/refresh"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (!response.ok) {
        await clearSession();
        return null;
      }
      const payload = await response.json() as SessionResponse;
      await saveSession(payload.access_token, payload.refresh_token);
      return payload.access_token;
    } catch (error) {
      // Un fallo de red no equivale a una sesión revocada: conservamos el refresh token.
      throw error;
    }
  })().finally(() => { refreshInFlight = null; });
  return refreshInFlight;
}

export async function mobileRequest<T>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  let access = await SecureStore.getItemAsync(ACCESS_KEY);
  if (!access) access = await refreshSession() ?? undefined;
  const request = (token?: string) => apiRequest<T>(path, {
    baseUrl: API_URL,
    method: options.method,
    body: options.body,
    token,
  });
  try {
    return await request(access ?? undefined);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    const nextAccess = await refreshSession();
    if (!nextAccess) {
      await clearSession();
      throw error;
    }
    return request(nextAccess);
  }
}

export async function authenticateMobile(mode: "login" | "register", credentials: Credentials): Promise<User> {
  const response = await fetch(apiUrl(`/auth/session/${mode}`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(credentials),
  });
  const payload = await response.json() as SessionResponse | { detail?: string };
  if (!response.ok) {
    throw new Error("detail" in payload && payload.detail ? payload.detail : "No se pudo iniciar sesión");
  }
  const session = payload as SessionResponse;
  await saveSession(session.access_token, session.refresh_token);
  return session.user;
}

export async function restoreMobileSession(): Promise<User | null> {
  const access = await SecureStore.getItemAsync(ACCESS_KEY);
  if (!access && !(await SecureStore.getItemAsync(REFRESH_KEY))) return null;
  try {
    return await mobileRequest<User>("/auth/me");
  } catch {
    return null;
  }
}

export async function completeMobileOnboarding(input: OnboardingIn) {
  return mobileRequest<components["schemas"]["OnboardingOut"]>("/onboarding", {
    method: "POST",
    body: input,
  });
}

export async function logoutMobile() {
  const refresh = await SecureStore.getItemAsync(REFRESH_KEY);
  const access = await SecureStore.getItemAsync(ACCESS_KEY);
  try {
    if (refresh) {
      await apiRequest<void>("/auth/session/logout", {
        baseUrl: API_URL,
        method: "POST",
        body: { refresh_token: refresh },
        token: access ?? undefined,
      });
    }
  } finally {
    await clearSession();
  }
}
