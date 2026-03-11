import { expect, test } from "@playwright/test";

test("settings menampilkan empty state untuk setup signals saat belum ada event konfigurasi", async ({ page }) => {
  await page.goto("/settings");

  await expect(page.getByRole("heading", { name: "Recent setup signals" })).toBeVisible();
  await expect(page.getByText("Belum ada event konfigurasi terbaru yang bisa ditampilkan.")).toBeVisible();
});
