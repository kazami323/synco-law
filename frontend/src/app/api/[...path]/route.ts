/**
 * Прокси всех /api/* запросов на бэкенд. Ручной (а не rewrites в
 * next.config), потому что rewrite пересобирает путь и теряет
 * завершающий слэш, а FastAPI различает /api/contracts и /api/contracts/
 * и отвечает редиректом — в браузере это заканчивалось циклом 308↔307.
 * Здесь путь передаётся байт-в-байт.
 */
import type { NextRequest } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

// Эти заголовки нельзя пересылать как есть: их выставляет сам fetch,
// а content-encoding уже "снят" при декодировании ответа
const SKIP_REQUEST = new Set(["host", "connection", "content-length"]);
const SKIP_RESPONSE = new Set([
  "content-encoding",
  "content-length",
  "transfer-encoding",
  "connection",
]);

async function proxy(req: NextRequest) {
  const url = new URL(req.url);
  const target = `${BACKEND}${url.pathname}${url.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!SKIP_REQUEST.has(key.toLowerCase())) headers.set(key, value);
  });

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstream = await fetch(target, {
    method: req.method,
    headers,
    body: hasBody ? await req.arrayBuffer() : undefined,
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!SKIP_RESPONSE.has(key.toLowerCase())) responseHeaders.set(key, value);
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
  proxy as HEAD,
  proxy as OPTIONS,
};
