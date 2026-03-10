import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock3,
  PlayCircle,
  RefreshCw,
  ShieldAlert,
  UsersRound,
  Workflow,
} from "lucide-react";

type AttentionLevel = "critical" | "high" | "medium";
type RunState = "Failed" | "Recovered" | "Running" | "Queued";

const attentionItems: Array<{
  title: string;
  detail: string;
  owner: string;
  level: AttentionLevel;
}> = [
  {
    title: "Primary account missing",
    detail: "Nadira House has scheduled output but no primary publishing account on Instagram.",
    owner: "Portfolio",
    level: "critical",
  },
  {
    title: "Workflow paused after validation drift",
    detail: "Affiliate refresh for Reza Atelier stopped after repeated schema mismatch on the landing payload.",
    owner: "Workflow",
    level: "high",
  },
  {
    title: "Approval queue waiting on operator handoff",
    detail: "Two recovery proposals are ready, but neither has an assignee for manual approval.",
    owner: "Incidents",
    level: "medium",
  },
];

const portfolioRows = [
  {
    name: "Nadira House",
    platform: "Instagram + TikTok",
    coverage: "3/4 accounts ready",
    health: "Needs primary account",
  },
  {
    name: "Reza Atelier",
    platform: "Instagram + YouTube",
    coverage: "4/4 accounts ready",
    health: "Stable",
  },
  {
    name: "Kala Studio",
    platform: "TikTok Shop",
    coverage: "2/3 accounts ready",
    health: "Recovery in progress",
  },
];

const workflowRows = [
  {
    name: "Launch cadence",
    status: "Healthy",
    detail: "Next content batch closes in 2 hours.",
  },
  {
    name: "Affiliate refresh",
    status: "Attention",
    detail: "Waiting for payload review before retry.",
  },
  {
    name: "Inbound qualification",
    status: "Healthy",
    detail: "Lead triage is within operator SLA.",
  },
];

const runRows: Array<{
  name: string;
  state: RunState;
  time: string;
  note: string;
}> = [
  {
    name: "Affiliate refresh / Reza Atelier",
    state: "Failed",
    time: "09:12",
    note: "Schema mismatch on downstream payload.",
  },
  {
    name: "Inbound qualification / Kala Studio",
    state: "Recovered",
    time: "08:44",
    note: "Recovery accepted and rerun completed.",
  },
  {
    name: "Daily posting plan / Nadira House",
    state: "Running",
    time: "08:10",
    note: "Asset assembly is still in progress.",
  },
  {
    name: "Comment moderation / Reza Atelier",
    state: "Queued",
    time: "07:58",
    note: "Awaiting next scheduler slot.",
  },
];

const attentionToneClass: Record<AttentionLevel, string> = {
  critical: "border-rose-200 bg-rose-50 text-rose-700",
  high: "border-amber-200 bg-amber-50 text-amber-700",
  medium: "border-slate-200 bg-slate-100 text-slate-700",
};

const runToneClass: Record<RunState, string> = {
  Failed: "bg-rose-100 text-rose-700",
  Recovered: "bg-emerald-100 text-emerald-700",
  Running: "bg-sky-100 text-sky-700",
  Queued: "bg-slate-100 text-slate-700",
};

export default function OverviewPage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-[28px] border border-slate-200 bg-white/90 px-6 py-6 shadow-[0_12px_40px_rgba(15,23,42,0.05)] sm:px-8">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
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
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-950 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
            >
              Open roster
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/runs"
              className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              Recent runs
              <PlayCircle className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
        <div className="flex flex-col gap-2 border-b border-slate-100 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
              Needs attention
            </p>
            <h3 className="mt-1 text-xl font-semibold tracking-[-0.02em] text-slate-950">
              Action queue
            </h3>
          </div>
          <p className="text-sm text-slate-500">3 items waiting for operator review</p>
        </div>

        <div className="mt-5 grid gap-3 lg:grid-cols-3">
          {attentionItems.map((item) => (
            <article
              key={item.title}
              className="flex h-full flex-col gap-4 rounded-[24px] border border-slate-200 bg-[#fbfbf8] p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.16em] text-slate-500">{item.owner}</p>
                  <h4 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-slate-950">
                    {item.title}
                  </h4>
                </div>
                <span
                  className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium capitalize ${attentionToneClass[item.level]}`}
                >
                  {item.level}
                </span>
              </div>

              <p className="text-sm leading-6 text-slate-600">{item.detail}</p>

              <div className="mt-auto flex flex-wrap gap-2">
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full bg-slate-950 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
                >
                  Review
                  <ArrowRight className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                >
                  Assign
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                Portfolio status
              </p>
              <h3 className="mt-1 text-xl font-semibold tracking-[-0.02em] text-slate-950">
                Coverage across active influencers
              </h3>
            </div>
            <UsersRound className="h-5 w-5 text-slate-400" />
          </div>

          <div className="mt-5 space-y-3">
            {portfolioRows.map((row) => (
              <article
                key={row.name}
                className="grid gap-3 rounded-[22px] border border-slate-200 bg-slate-50/80 p-4 md:grid-cols-[minmax(0,1fr)_auto]"
              >
                <div>
                  <h4 className="text-base font-semibold text-slate-950">{row.name}</h4>
                  <p className="mt-1 text-sm text-slate-600">{row.platform}</p>
                </div>
                <div className="flex flex-col items-start gap-1 md:items-end">
                  <span className="rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-700">
                    {row.coverage}
                  </span>
                  <span className="text-sm text-slate-500">{row.health}</span>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 pb-4">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
                Workflow health
              </p>
              <h3 className="mt-1 text-xl font-semibold tracking-[-0.02em] text-slate-950">
                Active automation lanes
              </h3>
            </div>
            <Workflow className="h-5 w-5 text-slate-400" />
          </div>

          <div className="mt-5 space-y-3">
            {workflowRows.map((row) => {
              const healthy = row.status === "Healthy";

              return (
                <article
                  key={row.name}
                  className="rounded-[22px] border border-slate-200 bg-[#f8f8f4] p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h4 className="text-base font-semibold text-slate-950">{row.name}</h4>
                      <p className="mt-1 text-sm text-slate-600">{row.detail}</p>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${
                        healthy ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {healthy ? <CheckCircle2 className="h-3.5 w-3.5" /> : <ShieldAlert className="h-3.5 w-3.5" />}
                      {row.status}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      </div>

      <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
        <div className="flex flex-col gap-2 border-b border-slate-100 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">
              Recent runs
            </p>
            <h3 className="mt-1 text-xl font-semibold tracking-[-0.02em] text-slate-950">
              Execution history that still needs context
            </h3>
          </div>
          <p className="text-sm text-slate-500">Queue, recovery, and retry context in one place</p>
        </div>

        <div className="mt-5 grid gap-3">
          {runRows.map((row) => (
            <article
              key={`${row.name}-${row.time}`}
              className="grid gap-3 rounded-[22px] border border-slate-200 bg-white p-4 md:grid-cols-[minmax(0,1fr)_auto]"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-base font-semibold text-slate-950">{row.name}</h4>
                  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${runToneClass[row.state]}`}>
                    {row.state}
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-slate-600">{row.note}</p>
              </div>
              <div className="flex items-center justify-between gap-3 md:flex-col md:items-end">
                <span className="inline-flex items-center gap-1 text-sm text-slate-500">
                  {row.state === "Queued" ? <Clock3 className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />}
                  {row.time}
                </span>
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100"
                >
                  Inspect
                </button>
              </div>
            </article>
          ))}
        </div>

        <div className="mt-6 flex items-center gap-2 text-sm text-slate-500">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          Recovery proposals stay in context here until the operator accepts or dismisses them.
        </div>
      </section>
    </div>
  );
}
