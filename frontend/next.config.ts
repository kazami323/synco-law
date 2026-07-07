import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Бэкенд различает /api/contracts и /api/contracts/ — не даём Next
  // резать завершающий слэш 308-редиректом, иначе запросы зацикливаются
  skipTrailingSlashRedirect: true,
  // Сам прокси /api/* живёт в src/app/api/[...path]/route.ts —
  // так один публичный адрес обслуживает и интерфейс, и API без CORS
};

export default nextConfig;
