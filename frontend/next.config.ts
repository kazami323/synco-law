import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Бэкенд различает /api/contracts и /api/contracts/ — не даём Next
  // резать завершающий слэш 308-редиректом, иначе запросы зацикливаются
  skipTrailingSlashRedirect: true,
  // Прокси /api/* остаётся fallback для локального и full-stack запуска.
  // Ahost-сборка обращается напрямую к NEXT_PUBLIC_API_URL на OVH.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' https: wss://127.0.0.1:64443; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
          },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          {
            key: "Strict-Transport-Security",
            value: "max-age=31536000; includeSubDomains",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
