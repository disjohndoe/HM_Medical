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

export class CezihApiError extends Error {
  cezih_error?: { code: string; display: string; diagnostics: string };
  constructor(message: string, cezih_error?: { code: string; display: string; diagnostics: string }) {
    super(message);
    this.name = "CezihApiError";
    this.cezih_error = cezih_error;
  }
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
    // Sanitize — strip anything that looks like an internal path, SQL, or traceback
    // But allow CEZIH/FHIR error messages that contain URLs (http://, urn:)
    if (detail.includes("Traceback") || detail.includes("SELECT")) {
      return "Došlo je do greške. Pokušajte ponovo."
    }
    if (/[\\]/.test(detail) || (/[/]/.test(detail) && !detail.includes("CEZIH") && !detail.includes("FHIR") && !detail.includes("http") && !detail.includes("urn:") && !detail.includes("Agent"))) {
      return "Došlo je do greške. Pokušajte ponovo."
    }
    return detail
  }
  if (typeof detail === "object" && detail !== null && "message" in detail) {
    return (detail as { message: string }).message
  }
  return "Došlo je do greške. Pokušajte ponovo."
}

function throwApiError(status: number, errorBody: { detail?: unknown } | null): never {
  if (!errorBody?.detail) {
    throw new Error(`API error: ${status}`);
  }
  const detail = errorBody.detail;
  if (typeof detail === "object" && detail !== null && "cezih_error" in detail) {
    const d = detail as { message: string; cezih_error: { code: string; display: string; diagnostics: string } };
    throw new CezihApiError(d.message, d.cezih_error);
  }
  throw new Error(extractErrorMessage(detail));
}

function handleAuthFailure(): never {
  document.cookie = "has_session=; path=/; SameSite=Lax; max-age=0";
  // Prevent redirect loop — only redirect if not already on login page
  if (!window.location.pathname.startsWith("/prijava")) {
    localStorage.setItem("auth_redirect_reason", "session_expired");
    localStorage.setItem("auth_redirect_reason_ts", Date.now().toString());
    window.location.href = "/prijava";
  }
  throw new Error("Sesija je istekla");
}

/**
 * Check if an error message is related to CEZIH signing configuration.
 * Returns the error message if it's a signing error, null otherwise.
 */
export function isSigningError(message: string): boolean {
  const signingKeywords = [
    "potpis nije konfiguriran",
    "korisnik nema konfiguriran način potpisa",
    "nema prijavljenog korisnika za potpisivanje",
    "baza podataka nije dostupna",
  ];
  const lowerMessage = message.toLowerCase();
  return signingKeywords.some((keyword) => lowerMessage.includes(keyword));
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
    const endpointName = endpoint.split("/").pop() || endpoint
    throw new Error(`Greška u komunikaciji s poslužiteljem (${endpointName}). Provjerite mrežnu vezu i pokušajte ponovo.`);
  }

  // Only skip refresh for login/register (no session to refresh).
  // /auth/me and other auth endpoints SHOULD trigger refresh when token expired.
  const isAuthFlowEndpoint = endpoint === "/auth/login" || endpoint === "/auth/register";
  if (res.status === 401 && !isAuthFlowEndpoint) {
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
        throwApiError(retryRes.status, errorBody);
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
    throwApiError(res.status, errorBody);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

async function apiClientRaw(
  endpoint: string,
  options?: { method?: string; body?: unknown },
): Promise<Response> {
  const method = options?.method || "GET";
  const headers: Record<string, string> = {};
  const fetchBody = options?.body ? JSON.stringify(options.body) : undefined;
  if (fetchBody) headers["Content-Type"] = "application/json";

  let res = await fetch(`${API_BASE}${endpoint}`, {
    method,
    credentials: "include",
    headers,
    body: fetchBody,
  });

  if (res.status === 401) {
    try {
      await refreshTokens();

      res = await fetch(`${API_BASE}${endpoint}`, {
        method,
        credentials: "include",
        headers,
        body: fetchBody,
      });

      if (!res.ok) {
        const errorBody = await res.json().catch(() => null);
        throwApiError(res.status, errorBody);
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
    throwApiError(res.status, errorBody);
  }

  return res;
}

async function apiClientFormData<T>(endpoint: string, formData: FormData): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      credentials: "include",
      body: formData,
    });
  } catch {
    throw new Error("Greška u komunikaciji s poslužiteljem. Provjerite mrežnu vezu i pokušajte ponovo.");
  }

  if (res.status === 401) {
    try {
      await refreshTokens();

      const retryRes = await fetch(`${API_BASE}${endpoint}`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (!retryRes.ok) {
        const errorBody = await retryRes.json().catch(() => null);
        throwApiError(retryRes.status, errorBody);
      }
      if (retryRes.status === 204) return undefined as T;
      return retryRes.json();
    } catch (err) {
      if (err instanceof Error && err.message === "Refresh failed") {
        handleAuthFailure();
      }
      throw err;
    }
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => null);
    throwApiError(res.status, errorBody);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
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
  postRaw: (endpoint: string, body: unknown) =>
    apiClientRaw(endpoint, { method: "POST", body }),
  postFormData: <T>(endpoint: string, formData: FormData) =>
    apiClientFormData<T>(endpoint, formData),
};
