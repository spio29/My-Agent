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

test("overview uses the dark avant workspace framing", async ({ page }) => {
  await page.goto("/");

  await expect(page.locator("body")).toHaveAttribute("data-shell-tone", "dark-avant");
  await expect(page.getByRole("heading", { name: "Action ribbon", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Incident spine", exact: true })).toBeVisible();
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

test("workflows and runs pages support operator inspection", async ({ page }) => {
  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "Workflows", exact: true })).toBeVisible();
  await expect(page.getByText("Active workflows")).toBeVisible();

  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "Runs", exact: true })).toBeVisible();
  await expect(page.getByPlaceholder("Search runs")).toBeVisible();
});

test("incidents and settings support operator follow-up", async ({ page }) => {
  await page.goto("/incidents");
  await expect(page.getByRole("heading", { name: "Incidents", exact: true })).toBeVisible();
  await expect(page.getByText("Recovery", { exact: true })).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Configuration", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Delivery lanes", exact: true })).toBeVisible();
  await expect(page.locator("body")).not.toContainText(/MCP|Template catalog|Integration inventory|provider template/i);
});
