import fs from "node:fs";
import { defineConfig, devices } from "@playwright/test";

const defaultApiPort = process.env.E2E_API_PORT || "18001";
const uiUrl = process.env.E2E_UI_BASE_URL || "http://127.0.0.1:5178";
const apiUrl = process.env.E2E_API_BASE_URL || `http://127.0.0.1:${defaultApiPort}`;
const apiHealthUrl = `${apiUrl}/healthz`;
const isWindows = process.platform === "win32";
const pythonExecutable = isWindows ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";
const resolvedApiPort = (() => {
  try {
    const parsed = new URL(apiUrl);
    return parsed.port || (parsed.protocol === "https:" ? "443" : "80");
  } catch {
    return defaultApiPort;
  }
})();
const apiCommand = `${pythonExecutable} -m uvicorn app.services.api.main:app --host 127.0.0.1 --port ${resolvedApiPort}`;
const uiCommand = isWindows
  ? "cmd /c npm run build && npx next start -H 127.0.0.1 -p 5178"
  : "npm run build && npx next start -H 127.0.0.1 -p 5178";
const systemChromeExists = fs.existsSync("/opt/google/chrome/chrome");
const useSystemChrome =
  process.env.E2E_USE_SYSTEM_CHROME === "0"
    ? false
    : process.env.E2E_USE_SYSTEM_CHROME === "1"
      ? true
      : systemChromeExists;
const chromiumProjectUse = useSystemChrome
  ? { ...devices["Desktop Chrome"], channel: "chrome" }
  : { ...devices["Desktop Chrome"] };

export default defineConfig({
  testDir: "./e2e",
  workers: process.env.CI ? 1 : undefined,
  retries: process.env.CI ? 1 : 0,
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  reporter: process.env.CI
    ? [
        ["list"],
        ["html", { outputFolder: "playwright-report", open: "never" }],
      ]
    : "list",
  use: {
    baseURL: uiUrl,
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: chromiumProjectUse,
    },
  ],
  webServer: [
    {
      command: apiCommand,
      cwd: "..",
      url: apiHealthUrl,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: uiCommand,
      cwd: ".",
      url: uiUrl,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_BASE: apiUrl,
      },
      reuseExistingServer: true,
      timeout: 180_000,
    },
  ],
});
