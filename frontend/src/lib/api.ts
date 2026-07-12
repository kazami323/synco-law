const API_URL = process.env.NEXT_PUBLIC_API_URL || "";
const UPLOAD_API_URL = process.env.NEXT_PUBLIC_UPLOAD_API_URL || API_URL;

export class ApiError extends Error {
  status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

function responseDetail(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object" || !("detail" in data)) return fallback;
  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) =>
        item && typeof item === "object" && "msg" in item
          ? String((item as { msg: unknown }).msg)
          : "",
      )
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((response) => response.ok)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function api<T>(
  path: string,
  options: RequestOptions = {},
  retryAuth = true
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      credentials: "include",
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError(
      0,
      "Сервер недоступен. Проверьте, что backend запущен."
    );
  }

  if (
    res.status === 401 &&
    retryAuth &&
    !path.startsWith("/api/auth/login") &&
    !path.startsWith("/api/auth/refresh")
  ) {
    if (await refreshSession()) return api<T>(path, options, false);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = responseDetail(data, detail);
    } catch {
      // Keep statusText when response body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

/** Скачивание файла с Bearer-токеном (CSV-экспорт и т.п.). */
export async function apiDownload(path: string, filename: string): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, { credentials: "include" });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export interface ChatStreamResult<TSources = Array<Record<string, unknown>>> {
  reply: string;
  sources: TSources;
}

type ChatStreamEvent =
  | { type: "delta"; text: string }
  | { type: "done"; reply: string; sources: unknown }
  | { type: "error"; detail: string };

/**
 * Потоковый чат с агентом (SSE). Вызывает onDelta на каждый кусок текста,
 * резолвится финальным проверенным ответом. Бросает ApiError, если стрим
 * недоступен (например, старый бэкенд) — вызывающий код делает фолбэк.
 */
export async function apiChatStream<TSources = Array<Record<string, unknown>>>(
  body: unknown,
  onDelta: (text: string) => void,
  retryAuth = true
): Promise<ChatStreamResult<TSources>> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/agents/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Сервер недоступен. Проверьте, что backend запущен.");
  }
  if (res.status === 401 && retryAuth) {
    if (await refreshSession()) return apiChatStream(body, onDelta, false);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("auth:expired"));
    }
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = responseDetail(await res.json(), detail);
    } catch {
      // Keep statusText when response body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: ChatStreamResult<TSources> | null = null;

  const handleLine = (line: string) => {
    if (!line.startsWith("data:")) return;
    let event: ChatStreamEvent;
    try {
      event = JSON.parse(line.slice(5).trim());
    } catch {
      return;
    }
    if (event.type === "delta") onDelta(event.text);
    else if (event.type === "done")
      finalResult = {
        reply: event.reply,
        sources: (event.sources ?? []) as TSources,
      };
    else if (event.type === "error") throw new ApiError(502, event.detail);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) handleLine(line.trim());
  }
  if (buffer.trim()) handleLine(buffer.trim());

  if (!finalResult) {
    throw new ApiError(0, "Поток ответа оборвался. Попробуйте ещё раз.");
  }
  return finalResult;
}

const UPLOAD_NETWORK_ERROR =
  "Не удалось связаться с сервером обработки документов. Проверьте интернет и повторите — если не поможет, сервер сейчас недоступен.";

const externalUpload = () => Boolean(UPLOAD_API_URL && UPLOAD_API_URL !== API_URL);

async function uploadAuthHeaders(): Promise<Record<string, string>> {
  if (!externalUpload()) return {};
  const token = await api<{ upload_token: string }>("/api/auth/upload-token", {
    method: "POST",
  });
  return { Authorization: `Bearer ${token.upload_token}` };
}

/** Запрос к серверу загрузок: внешний хост с Bearer-токеном или same-origin. */
async function uploadRequest<T>(
  path: string,
  init: { method: "GET" | "POST"; body?: FormData },
  retryAuth = true
): Promise<T> {
  const headers = await uploadAuthHeaders();
  let res: Response;
  try {
    res = await fetch(`${UPLOAD_API_URL}${path}`, {
      method: init.method,
      headers,
      credentials: externalUpload() ? "omit" : "include",
      body: init.body,
    });
  } catch {
    throw new ApiError(0, UPLOAD_NETWORK_ERROR);
  }
  // Упавший upload-токен (TTL 5 мин) обновляем и пробуем ещё раз
  if (res.status === 401 && retryAuth && externalUpload()) {
    return uploadRequest<T>(path, init, false);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = responseDetail(data, detail);
    } catch {
      // Keep statusText when response body is not JSON.
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return uploadRequest<T>(path, { method: "POST", body: form });
}

export interface ParsedFile {
  filename: string;
  text: string;
  extraction_method: "text" | "ocr";
}

type ParseFileResponse =
  | ({ status: "done" } & ParsedFile)
  | { status: "processing"; job_id: string; filename: string }
  | { status: "error"; detail: string };

const PARSE_POLL_INTERVAL_MS = 3_000;
const PARSE_POLL_DEADLINE_MS = 10 * 60_000;

/**
 * Разбор документа для чата. Текстовые файлы возвращаются сразу; сканы
 * распознаются на сервере в фоне — здесь мы поллим статус короткими
 * запросами, которым не страшны таймауты туннеля и прокси.
 */
export async function apiParseFile(form: FormData): Promise<ParsedFile> {
  const first = await uploadRequest<ParseFileResponse>("/api/agents/parse-file", {
    method: "POST",
    body: form,
  });
  if (first.status === "done") return first;
  if (first.status === "error") throw new ApiError(422, first.detail);

  const deadline = Date.now() + PARSE_POLL_DEADLINE_MS;
  while (Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, PARSE_POLL_INTERVAL_MS));
    const status = await uploadRequest<ParseFileResponse>(
      `/api/agents/parse-file/jobs/${first.job_id}`,
      { method: "GET" }
    );
    if (status.status === "done") return status;
    if (status.status === "error") throw new ApiError(422, status.detail);
  }
  throw new ApiError(
    0,
    "Распознавание занимает слишком много времени. Попробуйте PDF меньшего размера или свяжитесь с администратором."
  );
}
