"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, Clock3, PlayCircle, RefreshCw, UsersRound, Workflow } from "lucide-react";

import DetailDrawer from "@/components/operator/detail-drawer";
import FilterBar, { type FilterItem } from "@/components/operator/filter-bar";
import SectionShell from "@/components/operator/section-shell";
import StatusPill from "@/components/operator/status-pill";

type AttentionLevel = "critical" | "high" | "medium";
type RunState = "Failed" | "Recovered" | "Running" | "Queued";
type DrawerTone = "neutral" | "info" | "success" | "warning" | "critical";

type AttentionItem = {
  id: string;
  title: string;
  detail: string;
  owner: "Portfolio" | "Workflow" | "Incidents";
  level: AttentionLevel;
  assignee: string;
  dueLabel: string;
  recommendation: string[];
  context: string[];
};

type RunItem = {
  id: string;
  name: string;
  state: RunState;
  time: string;
  note: string;
  owner: string;
  nextAction: string[];
  context: string[];
};

type DrawerContent = {
  title: string;
  subtitle: string;
  statusLabel: string;
  statusTone: DrawerTone;
  fields: Array<{ label: string; value: string }>;
  sections: Array<{ title: string; body: string[] }>;
};

const attentionItems: AttentionItem[] = [
  {
    id: "nadira-primary-account",
    title: "Primary account missing",
    detail: "Nadira House has scheduled output but no primary publishing account on Instagram.",
    owner: "Portfolio",
    level: "critical",
    assignee: "Unassigned",
    dueLabel: "Within 30 minutes",
    recommendation: [
      "Set one Instagram account as primary before the next publishing window closes.",
      "Confirm that fallback credentials are still valid before reopening the schedule.",
    ],
    context: [
      "The next campaign slot starts at 10:00 and the current publishing lane cannot resolve an account target.",
      "No scheduler or queue primitive needs to change here; this is an operator data fix.",
    ],
  },
  {
    id: "reza-workflow-validation",
    title: "Workflow paused after validation drift",
    detail: "Affiliate refresh for Reza Atelier stopped after repeated schema mismatch on the landing payload.",
    owner: "Workflow",
    level: "high",
    assignee: "Nadia",
    dueLabel: "Before next retry window",
    recommendation: [
      "Review the last failed payload and confirm the required fields are still present.",
      "If the schema changed intentionally, update the workflow mapping before retrying.",
    ],
    context: [
      "The queue and runner are still healthy; only one workflow lane is paused.",
      "A recovery proposal already exists but has not been approved by an operator.",
    ],
  },
  {
    id: "approval-handoff",
    title: "Approval queue waiting on operator handoff",
    detail: "Two recovery proposals are ready, but neither has an assignee for manual approval.",
    owner: "Incidents",
    level: "medium",
    assignee: "Shift handoff",
    dueLabel: "This shift",
    recommendation: [
      "Assign one operator for approval coverage and clear the two pending proposals.",
      "Add an owner note so the next shift does not re-triage the same incident.",
    ],
    context: [
      "The recovery proposals are ready to execute and blocked only on manual approval.",
    ],
  },
];

const portfolioRows = [
  {
    name: "Nadira House",
    platform: "Instagram + TikTok",
    coverage: "3/4 accounts ready",
    health: "Needs primary account",
    tone: "warning" as DrawerTone,
  },
  {
    name: "Reza Atelier",
    platform: "Instagram + YouTube",
    coverage: "4/4 accounts ready",
    health: "Stable",
    tone: "success" as DrawerTone,
  },
  {
    name: "Kala Studio",
    platform: "TikTok Shop",
    coverage: "2/3 accounts ready",
    health: "Recovery in progress",
    tone: "info" as DrawerTone,
  },
];

const workflowRows = [
  {
    name: "Launch cadence",
    status: "Healthy",
    detail: "Next content batch closes in 2 hours.",
    tone: "success" as DrawerTone,
  },
  {
    name: "Affiliate refresh",
    status: "Attention",
    detail: "Waiting for payload review before retry.",
    tone: "warning" as DrawerTone,
  },
  {
    name: "Inbound qualification",
    status: "Healthy",
    detail: "Lead triage is within operator SLA.",
    tone: "success" as DrawerTone,
  },
];

const runRows: RunItem[] = [
  {
    id: "run-affiliate-refresh",
    name: "Affiliate refresh / Reza Atelier",
    state: "Failed",
    time: "09:12",
    note: "Schema mismatch on downstream payload.",
    owner: "Workflow lane",
    nextAction: [
      "Compare the latest payload with the expected landing schema.",
      "Approve the existing recovery proposal after fields are reconciled.",
    ],
    context: [
      "This run failed after validation and did not enqueue downstream work.",
      "No backlog expansion is happening because retries are paused.",
    ],
  },
  {
    id: "run-inbound-recovered",
    name: "Inbound qualification / Kala Studio",
    state: "Recovered",
    time: "08:44",
    note: "Recovery accepted and rerun completed.",
    owner: "Incident recovery",
    nextAction: [
      "Confirm that the rerun output matches the expected qualification state.",
      "Close the incident after operator review.",
    ],
    context: [
      "The recovery already executed successfully and is waiting for closure.",
    ],
  },
  {
    id: "run-daily-posting",
    name: "Daily posting plan / Nadira House",
    state: "Running",
    time: "08:10",
    note: "Asset assembly is still in progress.",
    owner: "Scheduler",
    nextAction: [
      "Watch the current run until assets complete and account resolution succeeds.",
    ],
    context: [
      "No errors have been emitted yet, but the missing primary account remains a nearby risk.",
    ],
  },
  {
    id: "run-comment-moderation",
    name: "Comment moderation / Reza Atelier",
    state: "Queued",
    time: "07:58",
    note: "Awaiting next scheduler slot.",
    owner: "Queue",
    nextAction: [
      "Keep queued until scheduler capacity opens; no operator action required now.",
    ],
    context: [
      "This run is healthy and simply waiting for normal execution order.",
    ],
  },
];

const attentionFilters: FilterItem[] = [
  { label: "All", value: "all", count: attentionItems.length },
  {
    label: "Critical",
    value: "critical",
    count: attentionItems.filter((item) => item.level === "critical").length,
  },
  {
    label: "Workflow",
    value: "workflow",
    count: attentionItems.filter((item) => item.owner === "Workflow").length,
  },
  {
    label: "Portfolio",
    value: "portfolio",
    count: attentionItems.filter((item) => item.owner === "Portfolio").length,
  },
];

const runFilters: FilterItem[] = [
  { label: "All", value: "all", count: runRows.length },
  { label: "Failed", value: "failed", count: runRows.filter((item) => item.state === "Failed").length },
  { label: "Active", value: "active", count: runRows.filter((item) => item.state === "Running").length },
  {
    label: "Recovery",
    value: "recovery",
    count: runRows.filter((item) => item.state === "Recovered").length,
  },
];

const attentionToneMap: Record<AttentionLevel, DrawerTone> = {
  critical: "critical",
  high: "warning",
  medium: "info",
};

const runToneMap: Record<RunState, DrawerTone> = {
  Failed: "critical",
  Recovered: "success",
  Running: "info",
  Queued: "neutral",
};

function buildAttentionDrawer(item: AttentionItem): DrawerContent {
  return {
    title: item.title,
    subtitle: item.owner,
    statusLabel: item.level,
    statusTone: attentionToneMap[item.level],
    fields: [
      { label: "Owner", value: item.owner },
      { label: "Assignee", value: item.assignee },
      { label: "Target", value: item.dueLabel },
    ],
    sections: [
      { title: "Situation", body: [item.detail] },
      { title: "Recommended action", body: item.recommendation },
      { title: "Context", body: item.context },
    ],
  };
}

function buildRunDrawer(item: RunItem): DrawerContent {
  return {
    title: item.name,
    subtitle: item.owner,
    statusLabel: item.state,
    statusTone: runToneMap[item.state],
    fields: [
      { label: "Run state", value: item.state },
      { label: "Recorded at", value: item.time },
      { label: "Owner", value: item.owner },
    ],
    sections: [
      { title: "Latest note", body: [item.note] },
      { title: "Next operator step", body: item.nextAction },
      { title: "Context", body: item.context },
    ],
  };
}

export default function OverviewPage() {
  const [attentionFilter, setAttentionFilter] = useState("all");
  const [runFilter, setRunFilter] = useState("all");
  const [drawerContent, setDrawerContent] = useState<DrawerContent | null>(null);

  const visibleAttentionItems = attentionItems.filter((item) => {
    if (attentionFilter === "all") return true;
    if (attentionFilter === "critical") return item.level === "critical";
    if (attentionFilter === "workflow") return item.owner === "Workflow";
    if (attentionFilter === "portfolio") return item.owner === "Portfolio";
    return true;
  });

  const visibleRunRows = runRows.filter((item) => {
    if (runFilter === "all") return true;
    if (runFilter === "failed") return item.state === "Failed";
    if (runFilter === "active") return item.state === "Running";
    if (runFilter === "recovery") return item.state === "Recovered";
    return true;
  });

  return (
    <>
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Overview</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Workspace operator campuran untuk memantau portofolio influencer, workflow aktif,
              run terbaru, dan incident yang perlu tindakan cepat.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <Link
              href="/influencers"
              className="inline-flex items-center gap-2 rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              Open roster
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/runs"
              className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              Recent runs
              <PlayCircle className="h-4 w-4" />
            </Link>
          </div>
        </div>

        <SectionShell
          title="Needs attention"
          description="Item yang perlu tindakan operator sekarang, tanpa keluar dari konteks overview."
          actions={<span className="text-sm text-slate-500">{visibleAttentionItems.length} open</span>}
        >
          <FilterBar items={attentionFilters} value={attentionFilter} onChange={setAttentionFilter} />
          <div className="mt-4 divide-y divide-slate-200">
            {visibleAttentionItems.map((item) => (
              <article
                key={item.id}
                className="grid gap-4 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-start"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-base font-semibold text-slate-950">{item.title}</h4>
                    <StatusPill tone={attentionToneMap[item.level]}>{item.level}</StatusPill>
                    <span className="text-sm text-slate-500">{item.owner}</span>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{item.detail}</p>
                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
                    <span>Assignee: {item.assignee}</span>
                    <span>Target: {item.dueLabel}</span>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 md:justify-end">
                  <button
                    type="button"
                    onClick={() => setDrawerContent(buildAttentionDrawer(item))}
                    className="rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
                  >
                    Review
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    Assign
                  </button>
                </div>
              </article>
            ))}
          </div>
        </SectionShell>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <SectionShell
            title="Portfolio status"
            description="Ringkasan coverage akun dan binding yang paling dekat dengan tindakan operator."
            actions={<UsersRound className="h-4 w-4 text-slate-400" />}
          >
            <div className="space-y-3">
              {portfolioRows.map((row) => (
                <article
                  key={row.name}
                  className="grid gap-3 rounded-lg border border-slate-200 bg-stone-50 px-4 py-3 md:grid-cols-[minmax(0,1fr)_auto]"
                >
                  <div>
                    <h4 className="text-sm font-semibold text-slate-950">{row.name}</h4>
                    <p className="mt-1 text-sm text-slate-600">{row.platform}</p>
                  </div>
                  <div className="flex flex-col items-start gap-1 md:items-end">
                    <span className="text-sm text-slate-700">{row.coverage}</span>
                    <StatusPill tone={row.tone}>{row.health}</StatusPill>
                  </div>
                </article>
              ))}
            </div>
          </SectionShell>

          <SectionShell
            title="Workflow health"
            description="Lane aktif yang sedang stabil dan yang perlu verifikasi operator."
            actions={<Workflow className="h-4 w-4 text-slate-400" />}
          >
            <div className="space-y-3">
              {workflowRows.map((row) => (
                <article
                  key={row.name}
                  className="rounded-lg border border-slate-200 bg-white px-4 py-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-sm font-semibold text-slate-950">{row.name}</h4>
                    <StatusPill tone={row.tone}>{row.status}</StatusPill>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{row.detail}</p>
                </article>
              ))}
            </div>
          </SectionShell>
        </div>

        <SectionShell
          title="Recent runs"
          description="Run terbaru yang masih perlu konteks, retry, atau pengecekan hasil."
          actions={<span className="text-sm text-slate-500">{visibleRunRows.length} visible</span>}
        >
          <FilterBar items={runFilters} value={runFilter} onChange={setRunFilter} />
          <div className="mt-4 divide-y divide-slate-200">
            {visibleRunRows.map((row) => (
              <article
                key={row.id}
                className="grid gap-4 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-start"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="text-sm font-semibold text-slate-950">{row.name}</h4>
                    <StatusPill tone={runToneMap[row.state]}>{row.state}</StatusPill>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">{row.note}</p>
                </div>

                <div className="flex flex-wrap items-center gap-2 md:justify-end">
                  <span className="inline-flex items-center gap-1 text-sm text-slate-500">
                    {row.state === "Queued" ? (
                      <Clock3 className="h-4 w-4" />
                    ) : (
                      <RefreshCw className="h-4 w-4" />
                    )}
                    {row.time}
                  </span>
                  <button
                    type="button"
                    onClick={() => setDrawerContent(buildRunDrawer(row))}
                    className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                  >
                    Inspect
                  </button>
                </div>
              </article>
            ))}
          </div>
        </SectionShell>
      </div>

      <DetailDrawer
        open={Boolean(drawerContent)}
        title={drawerContent?.title || ""}
        subtitle={drawerContent?.subtitle}
        statusLabel={drawerContent?.statusLabel}
        statusTone={drawerContent?.statusTone}
        fields={drawerContent?.fields}
        sections={drawerContent?.sections}
        footer={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setDrawerContent(null)}
              className="rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              Done
            </button>
            <button
              type="button"
              onClick={() => setDrawerContent(null)}
              className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              Close
            </button>
          </div>
        }
        onClose={() => setDrawerContent(null)}
      />
    </>
  );
}
