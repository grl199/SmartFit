import { apiRequest, apiUpload, ApiError } from "@smartfit/api-client";
import type { components } from "@smartfit/contracts";

type Credentials = components["schemas"]["Credentials"];
type OnboardingInput = components["schemas"]["OnboardingIn"];

export { apiRequest, apiUpload, ApiError };

export async function authenticate(
  mode: "login" | "register",
  credentials: Credentials,
) {
  const response = await fetch(`/api/auth/${mode}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    cache: "no-store",
    body: JSON.stringify(credentials),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(payload.detail ?? "No se pudo iniciar sesión.", response.status);
  }
  return response.json() as Promise<{ user: components["schemas"]["UserOut"] }>;
}

export function completeOnboarding(input: OnboardingInput) {
  return apiRequest<components["schemas"]["OnboardingOut"]>("/onboarding", {
    method: "POST",
    body: input,
  });
}

export function getCurrentUser() {
  return apiRequest<components["schemas"]["UserOut"]>("/auth/me");
}

export async function logoutWebSession() {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin",
    cache: "no-store",
  });
}
