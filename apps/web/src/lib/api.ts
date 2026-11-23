import type { components } from "@smartfit/contracts";

type Credentials = components["schemas"]["Credentials"];
type OnboardingInput = components["schemas"]["OnboardingIn"];

const API_URL = "/api";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiRequest<T>(
  path: string,
  options: { method?: string; body?: unknown; token?: string } = {},
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Error de API (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload.detail === "string" ? payload.detail : message;
    } catch {
      // La respuesta puede no ser JSON.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, formData: FormData, token?: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Error de API (${response.status})`;
    try {
      const payload = await response.json();
      message = typeof payload.detail === "string" ? payload.detail : message;
    } catch {
      // La respuesta puede no ser JSON.
    }
    throw new ApiError(message, response.status);
  }

  return response.json() as Promise<T>;
}

export function authenticate(
  mode: "login" | "register",
  credentials: Credentials,
) {
  return apiRequest<components["schemas"]["TokenOut"]>(`/auth/${mode}`, {
    method: "POST",
    body: credentials,
  });
}

export function completeOnboarding(token: string, input: OnboardingInput) {
  return apiRequest<components["schemas"]["OnboardingOut"]>("/onboarding", {
    method: "POST",
    token,
    body: input,
  });
}

export function getCurrentUser(token: string) {
  return apiRequest<components["schemas"]["UserOut"]>("/auth/me", { token });
}
