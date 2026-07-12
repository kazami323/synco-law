import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:3010";
const localRun = !process.env.PLAYWRIGHT_BASE_URL;
const backendPython = process.platform === "win32"
  ? ".\\.venv\\Scripts\\python.exe"
  : ".venv/bin/python";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["html", { open: "never" }], ["list"]] : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      testMatch: /product\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "mobile",
      testMatch: /mobile\.spec\.ts/,
      use: { ...devices["Pixel 7"] },
    },
  ],
  webServer: localRun
    ? [
        {
          command: `${backendPython} -m scripts.e2e_server`,
          cwd: path.resolve(__dirname, "../backend"),
          url: "http://127.0.0.1:8010/health/live",
          reuseExistingServer: true,
          timeout: 120_000,
          env: {
            ...process.env,
            DATABASE_URL:
              process.env.E2E_DATABASE_URL ??
              "postgresql+asyncpg://legal_user:secure_password@localhost:5432/legal_workspace_e2e",
            ENVIRONMENT: "test",
            APP_DEBUG: "false",
            RUN_BACKGROUND_JOBS: "false",
          },
        },
        {
          command: "npm run start -- --port 3010",
          cwd: __dirname,
          url: baseURL,
          reuseExistingServer: true,
          timeout: 120_000,
          env: {
            ...process.env,
            BACKEND_URL: "http://127.0.0.1:8010",
            NEXT_PUBLIC_API_URL: "",
            NEXT_PUBLIC_UPLOAD_API_URL: "",
          },
        },
      ]
    : undefined,
});
