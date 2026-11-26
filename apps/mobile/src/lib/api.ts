import { TokenStorage } from "./token-storage";
import type { components } from "@smartfit/contracts";
import { ApiError, apiRequest, type ApiRequestOptions } from "@smartfit/api-client";

const ACCESS_KEY = "smartfit.access-token";
const REFRESH_KEY = "smartfit.refresh-token";
export const API_BASE_URL = (process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export type SmartFitUser = components["schemas"]["UserOut"];
export type OnboardingPayload = components["schemas"]["OnboardingIn"];
export type SessionResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  user: SmartFitUser;
};

let refreshInFlight: Promise<SessionResponse | null> | null = null;
async function refreshSession(): Promise<SessionResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const refreshToken = await TokenStorage.getItemAsync(REFRESH_KEY);
      if (!refreshToken) return null;
      try {
        const result = await apiRequest<SessionResponse>("/auth/session/refresh", {
          method: "POST", body: { refresh_token: refreshToken }, baseUrl: API_BASE_URL
        });
        await TokenStorage.setItemAsync(ACCESS_KEY, result.access_token);
        await TokenStorage.setItemAsync(REFRESH_KEY, result.refresh_token);
        return result;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          await TokenStorage.deleteItemAsync(ACCESS_KEY);
          await TokenStorage.deleteItemAsync(REFRESH_KEY);
        }
        return null;
      }
    })().finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

export async function api<T>(path: string, token: string, options: Omit<ApiRequestOptions, "baseUrl" | "token"> = {}): Promise<T> {
  const request = (activeToken: string) => apiRequest<T>(path, { ...options, token: activeToken, baseUrl: API_BASE_URL });
  try {
    return await request(token);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || path.startsWith("/auth/session/")) throw error;
    const refreshed = await refreshSession();
    if (!refreshed) throw error;
    return request(refreshed.access_token);
  }
}
export function publicApi<T>(path: string, options: Omit<ApiRequestOptions, "baseUrl" | "token"> = {}): Promise<T> {
  return apiRequest<T>(path, { ...options, baseUrl: API_BASE_URL });
}

export async function apiUpload<T>(path: string, formData: FormData, token: string): Promise<T> {
  const send = (activeToken: string) => fetch(API_BASE_URL + path, {
    method: "POST",
    headers: { Authorization: "Bearer " + activeToken },
    body: formData,
  });
  let response = await send(token);
  if (response.status === 401 && !path.startsWith("/auth/session/")) {
    const refreshed = await refreshSession();
    if (refreshed) response = await send(refreshed.access_token);
  }
  if (!response.ok) {
    let message = "Error de API (" + response.status + ")";
    try {
      const payload: unknown = await response.json();
      if (payload && typeof payload === "object" && "detail" in payload && typeof payload.detail === "string") {
        message = payload.detail;
      }
    } catch {
      // La respuesta puede no ser JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export type TokenResponse = SessionResponse;
export type DashboardDay = {
  date: string;
  totals: {
    kcal: number; protein_g: number; carbs_g: number; sugars_g: number; fat_g: number;
    sat_fat_g: number; fiber_g: number; sodium_mg: number;
  };
  targets: {
    kcal: number; protein_g: number; carbs_g: number; fat_g: number; fiber_g?: number;
    water_ml?: number | null; workouts_per_week?: number;
  };
  entries: Array<{
    id: number; time: string; meal: string; food: string; brand?: string | null; grams: number;
    kcal: number; protein_g: number; carbs_g: number; sugars_g: number; fat_g: number;
    sat_fat_g: number; fiber_g: number; sodium_mg: number;
  }>;
  workouts: Array<{ id: number; kind: string; duration_min: number; kcal_burned?: number | null }>;
  water_ml: number;
};
export type FoodSearchResult = { id: number; name: string; brand?: string | null; kcal: number; protein_g: number; carbs_g: number; fat_g: number; icon?: string | null; image_url?: string | null; source?: string | null; barcode?: string | null };
export type WorkoutSummary = { id: number; kind: string; performed_on: string; duration_min: number; kcal_burned?: number | null; category?: string | null };
export type WeightEntry = { id: number; measured_on: string; weight_kg: number; body_fat_pct?: number | null };