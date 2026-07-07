import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Прокси API через фронтенд: браузер ходит на /api того же домена,
  // Next переправляет на бэкенд. Так один публичный адрес (туннель)
  // обслуживает и интерфейс, и API — без CORS.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
