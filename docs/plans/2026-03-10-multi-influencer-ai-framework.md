# Multi-Influencer AI Framework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the legacy SPIO-branded UI with a neutral, operator-first multi-influencer workspace that is build-stable, comfortable to use, and aligned with portfolio operations.

**Architecture:** Keep the existing generic backend primitives intact and reshape the UI around a neutral domain model. Replace the shell, route map, and interaction patterns first, then layer in page-specific adapters that reuse existing run, approval, and automation APIs where possible without reviving legacy product surfaces.

**Tech Stack:** Next.js App Router, React, TanStack Query, Tailwind CSS, Playwright, existing API proxy route in `ui/src/app/api/[...path]/route.ts`

---

### Task 1: Replace The Legacy Shell With A Neutral, Build-Stable Shell

**Files:**
- Modify: `ui/src/app/layout.tsx`
- Modify: `ui/src/app/globals.css`
- Modify: `ui/src/components/sidebar-nav.tsx`
- Modify: `ui/e2e/dashboard-pages.spec.ts`

**Step 1: Write the failing test**

Replace the current navigation assertions with a neutral shell assertion.

```ts
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
});
```

**Step 2: Run test to verify it fails**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: FAIL because the current shell still exposes legacy labels and old page routes.

**Step 3: Write minimal implementation**

- Remove `next/font/google` usage from `ui/src/app/layout.tsx`
- Replace the shell with a normal operator layout: fixed sidebar, simple header area, calm surfaces
- Rewrite `ui/src/app/globals.css` to remove glassmorphism, signature fonts, large radii, gradient-heavy shell styling, and old utility classes that encode the previous visual direction
- Update `ui/src/components/sidebar-nav.tsx` to the new route map and labels

Prefer a build-stable font strategy such as a local CSS stack. Do not introduce new external font fetches.

**Step 4: Run tests to verify it passes**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: PASS for the neutral navigation assertion.

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run build`

Expected: PASS, proving the shell no longer depends on remote Google font fetches.

**Step 5: Commit**

```bash
git add ui/src/app/layout.tsx ui/src/app/globals.css ui/src/components/sidebar-nav.tsx ui/e2e/dashboard-pages.spec.ts
git commit -m "refactor: replace legacy shell with neutral operator layout"
```

### Task 2: Create The New Route Map And Action-First Overview

**Files:**
- Modify: `ui/src/app/page.tsx`
- Create: `ui/src/app/influencers/page.tsx`
- Create: `ui/src/app/workflows/page.tsx`
- Create: `ui/src/app/incidents/page.tsx`
- Modify: `ui/src/components/sidebar-nav.tsx`
- Modify: `ui/e2e/dashboard-pages.spec.ts`

**Step 1: Write the failing test**

Add route coverage for the new pages and overview.

```ts
test("overview prioritizes actions and links to new routes", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText("Needs attention")).toBeVisible();

  await page.getByRole("link", { name: "Influencers" }).click();
  await expect(page).toHaveURL(/\/influencers$/);
  await expect(page.getByRole("heading", { name: "Influencers" })).toBeVisible();
});
```

**Step 2: Run test to verify it fails**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: FAIL because the overview content and new route pages do not exist yet.

**Step 3: Write minimal implementation**

- Replace `ui/src/app/page.tsx` with a neutral overview workspace
- Put the action queue at the top of the overview using real section labels such as `Needs attention`, `Portfolio status`, `Workflow health`, and `Recent runs`
- Create `ui/src/app/influencers/page.tsx`, `ui/src/app/workflows/page.tsx`, and `ui/src/app/incidents/page.tsx` with basic page shells and empty states
- Ensure `ui/src/components/sidebar-nav.tsx` links to the new pages

**Step 4: Run tests to verify it passes**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: PASS for the new overview and route coverage.

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run build`

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/src/app/page.tsx ui/src/app/influencers/page.tsx ui/src/app/workflows/page.tsx ui/src/app/incidents/page.tsx ui/src/components/sidebar-nav.tsx ui/e2e/dashboard-pages.spec.ts
git commit -m "feat: add neutral overview and route scaffolds"
```

### Task 3: Add Shared Operator Interaction Primitives

**Files:**
- Create: `ui/src/components/operator/detail-drawer.tsx`
- Create: `ui/src/components/operator/filter-bar.tsx`
- Create: `ui/src/components/operator/section-shell.tsx`
- Create: `ui/src/components/operator/status-pill.tsx`
- Modify: `ui/src/app/page.tsx`
- Modify: `ui/e2e/dashboard-pages.spec.ts`

**Step 1: Write the failing test**

Add an interaction test that proves overview items can be inspected without leaving the page.

```ts
test("overview opens action detail in a side panel", async ({ page }) => {
  await page.goto("/");

  await page.getByRole("button", { name: /review/i }).first().click();
  await expect(page.getByRole("complementary")).toBeVisible();
  await expect(page.getByText("Operator detail")).toBeVisible();
});
```

**Step 2: Run test to verify it fails**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: FAIL because the overview has no shared drawer or row-level operator interaction yet.

**Step 3: Write minimal implementation**

- Create reusable operator primitives for sections, filters, status pills, and a detail drawer
- Update `ui/src/app/page.tsx` to use those primitives
- Keep the motion restrained and context-preserving

The drawer should be functional, not theatrical: normal width, clear close action, and readable sections.

**Step 4: Run tests to verify it passes**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: PASS.

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run build`

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/src/components/operator/detail-drawer.tsx ui/src/components/operator/filter-bar.tsx ui/src/components/operator/section-shell.tsx ui/src/components/operator/status-pill.tsx ui/src/app/page.tsx ui/e2e/dashboard-pages.spec.ts
git commit -m "feat: add shared operator interaction primitives"
```

### Task 4: Build The Influencer Workspace With Neutral Adapters

**Files:**
- Modify: `ui/src/lib/api.ts`
- Create: `ui/src/lib/portfolio.ts`
- Modify: `ui/src/app/influencers/page.tsx`
- Modify: `ui/e2e/dashboard-pages.spec.ts`

**Step 1: Write the failing test**

Add a route test that verifies the new page behaves like a portfolio workspace instead of a legacy marketing surface.

```ts
test("influencers page shows list, detail, and account sections", async ({ page }) => {
  await page.goto("/influencers");

  await expect(page.getByRole("heading", { name: "Influencers" })).toBeVisible();
  await expect(page.getByText("Portfolio")).toBeVisible();
  await expect(page.getByText("Platform bindings")).toBeVisible();
  await expect(page.getByText("Accounts")).toBeVisible();
});
```

**Step 2: Run test to verify it fails**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: FAIL because the page is still only a scaffold.

**Step 3: Write minimal implementation**

- Add neutral frontend types and adapter helpers in `ui/src/lib/portfolio.ts`
- Extend `ui/src/lib/api.ts` only as needed to support neutral portfolio reads or safe empty-state behavior
- Turn `ui/src/app/influencers/page.tsx` into a master-detail workspace with:
  - searchable influencer list
  - selected influencer summary
  - platform binding section
  - account section

If dedicated portfolio endpoints are not ready yet, render useful empty states instead of fake populated dashboards.

**Step 4: Run tests to verify it passes**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: PASS.

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run build`

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/src/lib/api.ts ui/src/lib/portfolio.ts ui/src/app/influencers/page.tsx ui/e2e/dashboard-pages.spec.ts
git commit -m "feat: add influencer portfolio workspace"
```

### Task 5: Reframe Workflows And Runs Around Existing Generic Primitives

**Files:**
- Modify: `ui/src/lib/api.ts`
- Create: `ui/src/lib/workflows.ts`
- Modify: `ui/src/app/workflows/page.tsx`
- Modify: `ui/src/app/runs/page.tsx`
- Modify: `ui/e2e/dashboard-pages.spec.ts`

**Step 1: Write the failing test**

Add coverage for workflow and run inspection.

```ts
test("workflows and runs pages support operator inspection", async ({ page }) => {
  await page.goto("/workflows");
  await expect(page.getByRole("heading", { name: "Workflows" })).toBeVisible();
  await expect(page.getByText("Active workflows")).toBeVisible();

  await page.goto("/runs");
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expect(page.getByPlaceholder("Search runs")).toBeVisible();
});
```

**Step 2: Run test to verify it fails**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: FAIL because the pages do not yet expose the new operator framing.

**Step 3: Write minimal implementation**

- Add workflow adapter helpers in `ui/src/lib/workflows.ts`
- Reuse existing generic APIs from `ui/src/lib/api.ts` rather than inventing a SPIO-specific surface
- Update `ui/src/app/workflows/page.tsx` to present automation as workflows with clear filters and status presentation
- Update `ui/src/app/runs/page.tsx` to fit the calmer operator shell while preserving inspection utility

Preserve the underlying queue and run semantics. This is a presentation refactor, not a backend primitive rewrite.

**Step 4: Run tests to verify it passes**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: PASS.

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run build`

Expected: PASS.

**Step 5: Commit**

```bash
git add ui/src/lib/api.ts ui/src/lib/workflows.ts ui/src/app/workflows/page.tsx ui/src/app/runs/page.tsx ui/e2e/dashboard-pages.spec.ts
git commit -m "feat: adapt workflows and runs to operator workspace"
```

### Task 6: Build Incidents And Settings, Then Remove Obsolete Legacy Pages

**Files:**
- Modify: `ui/src/lib/api.ts`
- Create: `ui/src/lib/incidents.ts`
- Modify: `ui/src/app/incidents/page.tsx`
- Modify: `ui/src/app/settings/page.tsx`
- Delete: `ui/src/app/agents/page.tsx`
- Delete: `ui/src/app/armory/page.tsx`
- Delete: `ui/src/app/automation/page.tsx`
- Delete: `ui/src/app/connectors/page.tsx`
- Delete: `ui/src/app/experiments/page.tsx`
- Delete: `ui/src/app/jobs/page.tsx`
- Delete: `ui/src/app/memory/page.tsx`
- Delete: `ui/src/app/office/page.tsx`
- Delete: `ui/src/app/prompt/page.tsx`
- Delete: `ui/src/app/skills/page.tsx`
- Delete: `ui/src/app/team/page.tsx`
- Modify: `ui/e2e/dashboard-pages.spec.ts`

**Step 1: Write the failing test**

Replace the old route tests with incident and settings coverage.

```ts
test("incidents and settings support operator follow-up", async ({ page }) => {
  await page.goto("/incidents");
  await expect(page.getByRole("heading", { name: "Incidents" })).toBeVisible();
  await expect(page.getByText("Recovery")).toBeVisible();

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  await expect(page.getByText("Configuration")).toBeVisible();
});
```

**Step 2: Run test to verify it fails**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: FAIL because the incident surface is still incomplete and the test file still references old pages.

**Step 3: Write minimal implementation**

- Add neutral incident helpers in `ui/src/lib/incidents.ts`
- Update `ui/src/app/incidents/page.tsx` to show incident queue, recovery recommendation, and approval-aware action areas
- Simplify `ui/src/app/settings/page.tsx` into a neutral configuration page
- Remove obsolete legacy pages that no longer match the new information architecture
- Rewrite `ui/e2e/dashboard-pages.spec.ts` so it only validates the new route set

**Step 4: Run tests to verify it passes**

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run e2e -- dashboard-pages.spec.ts`

Expected: PASS.

Run: `cd /srv/apps/spio-agent-multi-influencer-v1/ui && npm run build`

Expected: PASS with only the new route set in place.

**Step 5: Commit**

```bash
git add ui/src/lib/api.ts ui/src/lib/incidents.ts ui/src/app/incidents/page.tsx ui/src/app/settings/page.tsx ui/e2e/dashboard-pages.spec.ts
git add -u ui/src/app
git commit -m "refactor: remove legacy surfaces and complete operator routes"
```
