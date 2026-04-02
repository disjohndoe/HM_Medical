const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
};

// BUG 2 fix: refresh lock — only one refresh at a time, others wait for its result
let refreshPromise: Promise<{ access_token: string; refresh_token: string }> | null = null;

async function doRefresh(): Promise<{ access_token: string; refresh_token: string }> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) throw new Error("No refresh token");

  const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!refreshRes.ok) {
    throw new Error("Refresh failed");
  }

  const tokens = await refreshRes.json();
  localStorage.setItem("access_token", tokens.access_token);
  localStorage.setItem("refresh_token", tokens.refresh_token);
  return tokens;
}

async function refreshTokens(): Promise<{ access_token: string; refresh_token: string }> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = doRefresh().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

function extractErrorMessage(detail: unknown): string {
  if (Array.isArray(detail)) {
    return detail.map((e: { msg?: string }) => e.msg || String(e)).join(", ")
  }
  if (typeof detail === "string") return detail
  return String(detail)
}

function handleAuthFailure(): never {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  document.cookie = "has_session=; path=/; SameSite=Lax; max-age=0";
  // MISSING 2: store reason so login page can show explanation
  localStorage.setItem("auth_redirect_reason", "session_expired");
  localStorage.setItem("auth_redirect_reason_ts", Date.now().toString());
  window.location.href = "/prijava";
  throw new Error("Sesija je istekla");
}

async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {} } = options;

  const accessToken = localStorage.getItem("access_token");

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  } catch {
    throw new Error("Greška u komunikaciji s poslužiteljem. Provjerite mrežnu vezu i pokušajte ponovo.");
  }

  if (res.status === 401 && !endpoint.startsWith("/auth/")) {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      try {
        const tokens = await refreshTokens();

        // Retry original request with new token
        const retryRes = await fetch(`${API_BASE}${endpoint}`, {
          method,
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${tokens.access_token}`,
            ...headers,
          },
          body: body ? JSON.stringify(body) : undefined,
        });

        if (!retryRes.ok) {
          const errorBody = await retryRes.json().catch(() => null);
          const message = errorBody?.detail ? extractErrorMessage(errorBody.detail) : `API error: ${retryRes.status} ${retryRes.statusText}`;
          throw new Error(message);
        }
        if (retryRes.status === 204) return undefined as T;
        return retryRes.json();
      } catch {
        // Refresh failed, clear tokens
      }
    }

    handleAuthFailure();
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => null);
    const message = errorBody?.detail ? extractErrorMessage(errorBody.detail) : `API error: ${res.status} ${res.statusText}`;
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function apiClientRaw(endpoint: string): Promise<Response> {
  const accessToken = localStorage.getItem("access_token");

  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  });

  if (res.status === 401) {
    const refreshToken = localStorage.getItem("refresh_token");
    if (refreshToken) {
      try {
        const tokens = await refreshTokens();

        const retryRes = await fetch(`${API_BASE}${endpoint}`, {
          headers: {
            Authorization: `Bearer ${tokens.access_token}`,
          },
        });

        if (!retryRes.ok) {
          const errorBody = await retryRes.json().catch(() => null);
          const message = errorBody?.detail ? extractErrorMessage(errorBody.detail) : `API error: ${retryRes.status} ${retryRes.statusText}`;
          throw new Error(message);
        }
        return retryRes;
      } catch {
        // Refresh failed, clear tokens
      }
    }

    handleAuthFailure();
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => null);
    const message = errorBody?.detail ? extractErrorMessage(errorBody.detail) : `API error: ${res.status} ${res.statusText}`;
    throw new Error(message);
  }

  return res;
}

export const api = {
  get: <T>(endpoint: string) => apiClient<T>(endpoint),
  post: <T>(endpoint: string, body: unknown) =>
    apiClient<T>(endpoint, { method: "POST", body }),
  put: <T>(endpoint: string, body: unknown) =>
    apiClient<T>(endpoint, { method: "PUT", body }),
  patch: <T>(endpoint: string, body: unknown) =>
    apiClient<T>(endpoint, { method: "PATCH", body }),
  delete: <T>(endpoint: string) =>
    apiClient<T>(endpoint, { method: "DELETE" }),
  fetchRaw: (endpoint: string) => apiClientRaw(endpoint),
};
