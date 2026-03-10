import { expect, test } from "@playwright/test";

test("overview shows neutral operator navigation", async ({ page }) => {
  await page.goto("/");
  const desktopNav = page.locator(".app-sidebar").getByRole("navigation", { name: "Primary" });

  for (const label of ["Overview", "Influencers", "Workflows", "Runs", "Incidents", "Settings"]) {
    await expect(desktopNav).toContainText(label);
  }
  await expect(page.locator("body")).not.toContainText(/Spio|Armory|Office|Team|Prompt/i);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  const mobileNav = page.locator(".app-mobile-shell").getByRole("navigation", { name: "Primary" });

  for (const label of ["Overview", "Influencers", "Workflows", "Runs", "Incidents", "Settings"]) {
    await expect(mobileNav).toContainText(label);
  }
});

test("overview prioritizes actions and links to new routes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Needs attention")).toBeVisible();

  await page.locator(".app-sidebar").getByRole("link", { name: "Influencers" }).click();
  await expect(page).toHaveURL(/\/influencers$/);
  await expect(page.getByRole("heading", { name: "Influencers" })).toBeVisible();
});

test("overview opens action detail in a side panel", async ({ page }) => {
  await page.goto("/");

  await page.locator("button:visible").filter({ hasText: /^Review$/ }).first().click();
  await expect(page.getByRole("complementary", { name: "Operator detail" })).toBeVisible();
  await expect(page.getByText("Operator detail")).toBeVisible();
});

test("influencers page shows list, detail, and account sections", async ({ page }) => {
  await page.goto("/influencers");

  await expect(page.getByRole("heading", { name: "Influencers" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Portfolio" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Platform bindings" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Accounts" })).toBeVisible();
});
