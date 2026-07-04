const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export function setToken(token: string | null) {
  if (token === null) localStorage.removeItem("token");
  else localStorage.setItem("token", token);
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(
      0,
      "Сервер недоступен. Проверьте, что backend запущен."
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data.detail) {
        detail =
          typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Keep statusText when response body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers,
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data.detail) {
        detail =
          typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Keep statusText when response body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}
