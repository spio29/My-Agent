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

test("overview prioritizes actions and links to new routes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Needs attention")).toBeVisible();

  await page.getByRole("link", { name: "Influencers" }).click();
  await expect(page).toHaveURL(/\/influencers$/);
  await expect(page.getByRole("heading", { name: "Influencers" })).toBeVisible();
});
