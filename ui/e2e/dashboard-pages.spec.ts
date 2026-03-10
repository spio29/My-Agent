import { expect, test } from "@playwright/test";

test("overview shows neutral operator navigation", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("navigation")).toContainText([
    "Overview",
    "Influencers",
    "Workflows",
    "Runs",
    "Incidents",
    "Settings",
  ]);
  await expect(page.locator("body")).not.toContainText(/Spio|Armory|Office|Team|Prompt/i);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();

  await expect(page.getByRole("navigation")).toContainText([
    "Overview",
    "Influencers",
    "Workflows",
    "Runs",
    "Incidents",
    "Settings",
  ]);
});
