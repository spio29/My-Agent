import fs from "node:fs";
import path from "node:path";

import { expect, request as playwrightRequest, test } from "@playwright/test";

const API_BASE = process.env.E2E_API_BASE_URL || "http://127.0.0.1:8000";
const ENV_FILES = [path.resolve(__dirname, "../.env.local"), path.resolve(__dirname, "../../.env")];

const bacaEnvDariFile = (key: string): string => {
  for (const filePath of ENV_FILES) {
    try {
      const body = fs.readFileSync(filePath, "utf-8");
      const match = body.match(new RegExp(`^${key}=(.*)$`, "m"));
      if (!match) continue;
      const raw = match[1].trim();
      if (!raw) continue;
      if ((raw.startsWith('"') && raw.endsWith('"')) || (raw.startsWith("'") && raw.endsWith("'"))) {
        return raw.slice(1, -1);
      }
      return raw;
    } catch {
      // ignore missing env files in CI/local variation
    }
  }
  return "";
};

const ambilEnv = (...keys: string[]) => {
  for (const key of keys) {
    const fromProcess = (process.env[key] || "").trim();
    if (fromProcess) return fromProcess;
    const fromFile = bacaEnvDariFile(key).trim();
    if (fromFile) return fromFile;
  }
  return "";
};

const resolveAuthToken = (): string => {
  const explicitAdmin = ambilEnv("E2E_ADMIN_TOKEN");
  if (explicitAdmin) return explicitAdmin;

  const rawApiKeys = ambilEnv("AUTH_API_KEYS");
  if (rawApiKeys) {
    const first = rawApiKeys.split(",")[0]?.trim() || "";
    if (first) {
      const tokenPart = first.includes(":") ? first.split(":", 1)[0].trim() : first;
      if (tokenPart) return tokenPart;
    }
  }

  return ambilEnv("E2E_API_TOKEN", "NEXT_PUBLIC_API_TOKEN");
};

const buildAuthHeaders = (): Record<string, string> => {
  const token = resolveAuthToken();
  if (!token) return {};

  const headerName = ambilEnv("E2E_API_AUTH_HEADER", "AUTH_TOKEN_HEADER") || "Authorization";
  const scheme = ambilEnv("E2E_API_AUTH_SCHEME", "AUTH_TOKEN_SCHEME") || "Bearer";
  const headerValue = scheme ? `${scheme} ${token}` : token;
  return { [headerName]: headerValue };
};

test("menampilkan update skill baru dari event backend di halaman setelan", async ({ page }) => {
  const accountId = `e2e_${Date.now()}`;
  const api = await playwrightRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: buildAuthHeaders() });

  try {
    const upsertResponse = await api.put(`/integrations/accounts/openai/${accountId}`, {
      data: {
        enabled: true,
        secret: "sk-e2e-test",
        config: { model_id: "gpt-4o-mini" },
      },
    });
    expect(
      upsertResponse.ok(),
      `PUT integration failed status=${upsertResponse.status()} body=${await upsertResponse.text()}`,
    ).toBeTruthy();

    await page.goto("/settings");

    await expect(page.getByRole("heading", { name: "Pembaruan Skill & Puzzle Terbaru" })).toBeVisible();
    await expect(page.getByText(new RegExp(`Akun integrasi openai/${accountId} diperbarui\\.`)).first()).toBeVisible();
  } finally {
    await api.delete(`/integrations/accounts/openai/${accountId}`);
    await api.dispose();
  }
});
