import { apiRequest, apiUpload, ApiError } from "@smartfit/api-client";
import type { components } from "@smartfit/contracts";

type Credentials = components["schemas"]["Credentials"];
type OnboardingInput = components["schemas"]["OnboardingIn"];

export { apiRequest, apiUpload, ApiError };

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
