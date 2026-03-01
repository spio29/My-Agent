import fs from "node:fs";
import path from "node:path";

import { expect, request as playwrightRequest, test } from "@playwright/test";

const API_BASE = process.env.E2E_API_BASE_URL || "http://127.0.0.1:8000";
const BATAS_JOBS = 20;
const BATAS_RUNS = 30;

const escapeRegex = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

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

const buildAuthHeaders = (): Record<string, string> => {
  const token = ambilEnv("E2E_API_TOKEN", "NEXT_PUBLIC_API_TOKEN");
  if (!token) return {};

  const headerName = ambilEnv("E2E_API_AUTH_HEADER", "AUTH_TOKEN_HEADER") || "Authorization";
  const scheme = ambilEnv("E2E_API_AUTH_SCHEME", "AUTH_TOKEN_SCHEME") || "Bearer";
  const headerValue = scheme ? `${scheme} ${token}` : token;
  return { [headerName]: headerValue };
};

const buildJobPayload = (jobId: string) => ({
  job_id: jobId,
  type: "monitor.channel",
  timeout_ms: 30000,
  retry_policy: { max_retry: 1, backoff_sec: [1] },
  inputs: {
    channel: "whatsapp",
    account_id: "default",
  },
});

test("halaman jobs mendukung pagination server-side", async ({ page }) => {
  const prefix = `e2e-paging-job-${Date.now()}`;
  const api = await playwrightRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: buildAuthHeaders() });
  const createdJobIds: string[] = [];

  try {
    for (let i = 0; i < 21; i += 1) {
      const suffix = String(i).padStart(2, "0");
      const jobId = `${prefix}-${suffix}`;
      createdJobIds.push(jobId);
      const response = await api.post("/jobs", { data: buildJobPayload(jobId) });
      expect(response.ok(), `POST /jobs failed status=${response.status()} body=${await response.text()}`).toBeTruthy();
    }

    await expect
      .poll(async () => {
        const response = await api.get(`/jobs?search=${encodeURIComponent(prefix)}&limit=100`);
        if (!response.ok()) return -1;
        const rows = (await response.json()) as Array<{ job_id: string }>;
        return rows.length;
      })
      .toBeGreaterThanOrEqual(21);

    const expectedPage1Count = (
      (await (await api.get(`/jobs?search=${encodeURIComponent(prefix)}&limit=${BATAS_JOBS}&offset=0`)).json()) as Array<
        { job_id: string }
      >
    ).length;
    const expectedPage2Count = (
      (await (await api.get(`/jobs?search=${encodeURIComponent(prefix)}&limit=${BATAS_JOBS}&offset=${BATAS_JOBS}`)).json()) as Array<
        { job_id: string }
      >
    ).length;

    await page.goto("/jobs");
    await page.getByPlaceholder("Cari job (job_id / type)...").fill(prefix);

    await expect(page.getByRole("heading", { level: 1, name: "Daftar Tugas" })).toBeVisible();
    await expect(
      page.getByText(new RegExp(`Halaman 1, menampilkan ${expectedPage1Count} job\\.`)).first(),
    ).toBeVisible();
    await expect(page.getByRole("cell", { name: `${prefix}-19` }).first()).toBeVisible();

    const tombolBerikutnya = page.getByRole("button", { name: "Berikutnya" });
    if (expectedPage2Count > 0) {
      await expect(tombolBerikutnya).toBeEnabled();
    } else {
      await expect(tombolBerikutnya).toBeDisabled();
      return;
    }
    await tombolBerikutnya.click();

    await expect(page.getByText(/^Halaman 2$/).first()).toBeVisible();
    await expect(
      page.getByText(new RegExp(`Halaman 2, menampilkan ${expectedPage2Count} job\\.`)).first(),
    ).toBeVisible();
    await expect(page.getByRole("cell", { name: `${prefix}-20` }).first()).toBeVisible();
    await expect(page.getByRole("cell", { name: new RegExp(`^${escapeRegex(prefix)}-00$`) })).not.toBeVisible();
  } finally {
    await Promise.all(
      createdJobIds.map((jobId) =>
        api.put(`/jobs/${encodeURIComponent(jobId)}/disable`, { data: {} }).catch(() => null),
      ),
    );
    await api.dispose();
  }
});

test("halaman runs mendukung pagination server-side", async ({ page }) => {
  const jobId = `e2e-paging-run-job-${Date.now()}`;
  const api = await playwrightRequest.newContext({ baseURL: API_BASE, extraHTTPHeaders: buildAuthHeaders() });

  try {
    const createJobResponse = await api.post("/jobs", { data: buildJobPayload(jobId) });
    expect(
      createJobResponse.ok(),
      `POST /jobs failed status=${createJobResponse.status()} body=${await createJobResponse.text()}`,
    ).toBeTruthy();

    for (let i = 0; i < 31; i += 1) {
      const runResponse = await api.post(`/jobs/${encodeURIComponent(jobId)}/run`);
      expect(
        runResponse.ok(),
        `POST /jobs/${jobId}/run failed status=${runResponse.status()} body=${await runResponse.text()}`,
      ).toBeTruthy();
    }

    const expectedPage1Count = (
      (await (await api.get(`/runs?job_id=${encodeURIComponent(jobId)}&limit=${BATAS_RUNS}&offset=0`)).json()) as Array<{
        run_id: string;
      }>
    ).length;
    const expectedPage2Count = (
      (
        await (await api.get(`/runs?job_id=${encodeURIComponent(jobId)}&limit=${BATAS_RUNS}&offset=${BATAS_RUNS}`)).json()
      ) as Array<{
        run_id: string;
      }>
    ).length;

    await page.goto("/runs");
    await page.getByPlaceholder("Filter job_id").fill(jobId);

    await expect(page.getByRole("heading", { level: 1, name: "Riwayat Eksekusi" })).toBeVisible();
    await expect(
      page.getByText(new RegExp(`Halaman 1, menampilkan ${expectedPage1Count} run\\.`)).first(),
    ).toBeVisible();
    await expect(page.getByRole("cell", { name: jobId }).first()).toBeVisible();

    const tombolBerikutnya = page.getByRole("button", { name: "Berikutnya" });
    if (expectedPage2Count > 0) {
      await expect(tombolBerikutnya).toBeEnabled();
    } else {
      await expect(tombolBerikutnya).toBeDisabled();
      return;
    }
    await tombolBerikutnya.click();

    await expect(page.getByText(/^Halaman 2$/).first()).toBeVisible();
    await expect(
      page.getByText(new RegExp(`Halaman 2, menampilkan ${expectedPage2Count} run\\.`)).first(),
    ).toBeVisible();
    await expect(page.locator("tbody tr")).toHaveCount(expectedPage2Count);
  } finally {
    await api.put(`/jobs/${encodeURIComponent(jobId)}/disable`, { data: {} }).catch(() => null);
    await api.dispose();
  }
});
