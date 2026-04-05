const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

type RequestOptions = {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
};

// Refresh lock — only one refresh at a time, others wait for its result
let refreshPromise: Promise<void> | null = null;

async function doRefresh(): Promise<void> {
  // refresh_token is sent automatically via httpOnly cookie (path=/api/auth)
  const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

  if (!refreshRes.ok) {
    throw new Error("Refresh failed");
  }
  // New tokens are set as httpOnly cookies by the server — nothing to store client-side
}

async function refreshTokens(): Promise<void> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = doRefresh().finally(() => {
    refreshPromise = null;
  });

  return refreshPromise;
}

function extractErrorMessage(detail: unknown): string {
  // Map backend validation errors to user-friendly messages
  // Never expose internal error details, schema info, or paths
  if (Array.isArray(detail)) {
    // Pydantic validation errors — show only field-level messages
    return detail
      .map((e: { msg?: string; loc?: string[] }) => e.msg || "")
      .filter(Boolean)
      .join(", ") || "Nevažeći podaci"
  }
  if (typeof detail === "string") {
    // Sanitize — strip anything that looks like a path, SQL, or internal detail
    if (/[\\/]/.test(detail) || detail.includes("Traceback") || detail.includes("SELECT")) {
      return "Došlo je do greške. Pokušajte ponovo."
    }
    return detail
  }
  return "Došlo je do greške. Pokušajte ponovo."
}

function handleAuthFailure(): never {
  document.cookie = "has_session=; path=/; SameSite=Lax; max-age=0";
  localStorage.setItem("auth_redirect_reason", "session_expired");
  localStorage.setItem("auth_redirect_reason_ts", Date.now().toString());
  window.location.href = "/prijava";
  throw new Error("Sesija je istekla");
}

async function apiClient<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {} } = options;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      method,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new Error("Greška u komunikaciji s poslužiteljem. Provjerite mrežnu vezu i pokušajte ponovo.");
  }

  if (res.status === 401 && !endpoint.startsWith("/auth/")) {
    try {
      await refreshTokens();

      // Retry original request — new access_token cookie is set by server
      const retryRes = await fetch(`${API_BASE}${endpoint}`, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
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
    } catch (err) {
      // If refresh itself failed (not a retry error), clear auth
      if (err instanceof Error && err.message === "Refresh failed") {
        handleAuthFailure();
      }
      throw err;
    }
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
  let res = await fetch(`${API_BASE}${endpoint}`, {
    credentials: "include",
  });

  if (res.status === 401) {
    try {
      await refreshTokens();

      res = await fetch(`${API_BASE}${endpoint}`, {
        credentials: "include",
      });

      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        const message = errorBody?.detail ? extractErrorMessage(errorBody.detail) : `API error: ${res.status} ${res.statusText}`;
        throw new Error(message);
      }
      return res;
    } catch (err) {
      if (err instanceof Error && err.message === "Refresh failed") {
        handleAuthFailure();
      }
      throw err;
    }
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
