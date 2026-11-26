export type ApiRequestOptions = {
  method?: string;
  body?: unknown;
  token?: string;
  baseUrl?: string;
  headers?: HeadersInit;
};

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function readError(response: Response): Promise<never> {
  let message = `Error de API (${response.status})`;
  try {
    const payload: unknown = await response.json();
    if (
      payload &&
      typeof payload === "object" &&
      "detail" in payload &&
      typeof payload.detail === "string"
    ) message = payload.detail;
  } catch {
    // La respuesta puede no ser JSON.
  }
  throw new ApiError(message, response.status);
}

// El refresh token rota en cada uso. Compartimos una única renovación entre
// las peticiones simultáneas para evitar que una segunda rotación invalide la primera.
let refreshInFlight: Promise<boolean> | null = null;

function refreshWebSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch("/api/auth/refresh", {
          method: "POST",
          credentials: "same-origin",
          cache: "no-store",
        });
        return response.ok;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

async function requestWithSessionRetry(
  input: RequestInfo | URL,
  init: RequestInit,
  canRefresh: boolean,
): Promise<Response> {
  let response = await fetch(input, init);
  if (response.status === 401 && canRefresh && await refreshWebSession()) {
    response = await fetch(input, init);
  }
  return response;
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const baseUrl = (options.baseUrl ?? "/api").replace(/\/+$/, "");
  const canRefresh = baseUrl === "/api" && !options.token && !path.startsWith("/auth/session/");
  const response = await requestWithSessionRetry(`${baseUrl}${path}`, {
    method: options.method ?? "GET",
    headers: {
      ...(options.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      ...options.headers,
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
    credentials: "same-origin",
  }, canRefresh);

  if (!response.ok) return readError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function apiUpload<T>(
  path: string,
  formData: FormData,
  token?: string,
  baseUrl = "/api",
): Promise<T> {
  const canRefresh = baseUrl === "/api" && !token;
  const response = await requestWithSessionRetry(`${baseUrl.replace(/\/+$/, "")}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
    cache: "no-store",
    credentials: "same-origin",
  }, canRefresh);

  if (!response.ok) return readError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
