# Multi-Influencer AI Framework Design

## Goal

Replace the legacy SPIO-branded dashboard with a neutral, operator-first workspace for managing a multi-influencer portfolio. The new UI must feel functional, interactive, and comfortable for long sessions while preserving the existing generic queue, runner, scheduler, auth, and API proxy primitives.

## Problem Summary

The current UI has two structural problems:

1. It still exposes legacy product surfaces and vocabulary such as `Spio`, `Armory`, `Office`, `Team`, and `Prompt`, which do not fit the multi-influencer portfolio model.
2. The shell is visually heavy and operationally brittle. `ui/src/app/layout.tsx` uses `next/font/google`, which breaks `next build` in environments without external DNS access, and the global styling relies on glass panels, gradients, signature fonts, and decorative framing that no longer match the product direction.

This is not a rename pass. It is a shell reset plus an information architecture reset.

## Product Direction

The dashboard is for operators, not for product marketing and not for branded storytelling. The first screen must help an operator answer these questions quickly:

- What needs action now?
- Which influencer, platform, or account is blocked?
- Which workflows and runs are failing or degrading?
- Which incidents and approvals are waiting for review?

The UI should support long-running operational use, so comfort matters as much as density. The preferred balance is intentionally spacious, readable, and calm rather than compressed into a control-room aesthetic.

## Design Principles

### 1. Neutral domain language

The UI must use portfolio and operations language:

- `Overview`
- `Influencers`
- `Workflows`
- `Runs`
- `Incidents`
- `Settings`

Legacy feature names and SPIO-specific surface metaphors should be removed from the main operator flow.

### 2. Action-first, not metric-first

The home screen should not begin with decorative KPI cards or fake telemetry. The topmost section should be an operator action queue showing the items that require decisions or recovery work now.

### 3. Comfortable long-session ergonomics

The layout should be roomy, legible, and steady:

- fixed-width sidebar with solid background and border-right
- straightforward headers
- low-motion interactions
- no oversized radii
- no glassmorphism
- no decorative hero block inside the app shell

### 4. Honest interactivity

Interactivity must serve work:

- quick filters
- row-level actions
- detail drawers or side panels that preserve context
- inline error and empty states
- optimistic feedback for safe actions

Avoid decorative movement, ornamental badges, or filler charts.

### 5. Build stability over visual novelty

The UI shell must not depend on remote Google font fetches. Use a local CSS stack or other build-stable font strategy that works in offline and restricted environments.

## Information Architecture

## Primary Navigation

- `Overview`
- `Influencers`
- `Workflows`
- `Runs`
- `Incidents`
- `Settings`

## Removed From Primary Navigation

- `Armory`
- `Office`
- `Team`
- `Prompt`
- `Memory`
- `Agents`
- `Jobs`
- `Connectors`
- `Experiments`
- `Skills`

Some generic backend capabilities that power those views may still exist behind the scenes, but they should not define the new operator model.

## Page Model

### Overview

The entry page is a mixed workspace. It combines portfolio and operations visibility, but items requiring action stay at the top.

Recommended sections:

- `Needs attention`: incident, approval, missing primary account, failing workflow, degraded run
- `Portfolio status`: influencer count, enabled platforms, account coverage, recent additions
- `Workflow health`: active workflows, paused workflows, recent failures, overdue work
- `Recent runs`: latest successful/failed executions with direct inspection access

### Influencers

This page should use a master-detail layout:

- left side or main table: influencer list with search and filter
- right side or drawer: selected influencer detail
- within detail: platform bindings, accounts, primary account status, objective summary

### Workflows

This page should present workflows as operator-managed automation units rather than raw jobs. Filters should focus on state, platform, objective, and owner context.

### Runs

This page should preserve the existing run primitive but surface it in a clearer operational format with filters, timeline-friendly columns, and expandable detail.

### Incidents

This page is the recovery and approval lane. It should highlight severity, recommended action, approval requirement, and latest operator note.

### Settings

This page remains administrative and low-frequency. It should keep configuration clear and calm without being promoted as part of the main operational loop.

## Interaction Model

## Shell

- left sidebar remains persistent on desktop
- mobile uses a simple collapsible nav, not a floating branded panel
- page header contains only the title, context text if necessary, and actions

## Detail access

Lists should not force constant page navigation. Use a drawer or side panel for:

- run detail
- incident detail
- influencer detail
- workflow detail

This preserves operator context and reduces “lost place” navigation.

## Feedback states

- loading state: skeleton or low-noise placeholder
- empty state: concrete explanation plus next action
- error state: inline panel with retry action
- success state: concise toast only when useful

## Visual Direction

The implementation should follow `uncodixfy`:

- normal sidebar
- normal headers
- normal cards and tables
- small-to-medium radii
- subtle borders
- restrained shadows
- calm colors
- no giant rounded glass islands
- no gradients used as the primary design language
- no “command center” theater

Typography should be stable and local. Prefer a clean sans-serif system stack or a local font strategy over remote font services.

## Data And API Strategy

The redesign must preserve existing generic backend primitives. The UI should adapt them instead of forcing a premature backend rewrite:

- `Runs` should continue to use the existing run APIs
- workflow views can adapt existing job or automation endpoints where appropriate
- approval and incident-style views should reuse safe existing approval/audit primitives where possible
- neutral portfolio-specific adapters may be added in the UI layer until dedicated `/portfolio/*` endpoints land

The API proxy route in `ui/src/app/api/[...path]/route.ts` stays in place.

## Legacy Cleanup Scope

The redesign intentionally removes the old branded UI shell and its supporting routes from the main experience. Deleting obsolete page files is preferred over keeping dead surfaces around and hiding them in navigation.

The cleanup should include:

- external Google font imports
- legacy SPIO labels and branding
- glassmorphism shell styles
- oversized decorative radii
- legacy navigation items and their tests
- stale page routes that no longer match the product model

## Testing And Verification

The redesign should be driven by TDD at the route and interaction level.

Minimum verification for each implementation task:

- Playwright route or interaction test added first and verified red
- targeted Playwright re-run verified green
- `npm run build` verified green after shell or route changes

The UI should also degrade gracefully when neutral backend endpoints are not ready yet. Empty states are acceptable; fake dashboards are not.

## Non-Goals

- Rebuilding queue, runner, scheduler, or auth primitives
- Rebranding the backend around SPIO-specific terms
- Adding decorative analytics that do not support operator action
- Preserving legacy page names just for continuity

## Deliverable Summary

The new frontend should feel like a calm operational workspace for a multi-influencer portfolio:

- neutral language
- action-first overview
- comfortable long-session layout
- drawer-based detail flow
- no product-theater visuals
- stable offline-capable build behavior
