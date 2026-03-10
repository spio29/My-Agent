"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";

import FilterBar from "@/components/operator/filter-bar";
import SectionShell from "@/components/operator/section-shell";
import StatusPill from "@/components/operator/status-pill";
import { getJobs } from "@/lib/api";
import {
  adaptWorkflowJobs,
  matchesWorkflowSearch,
  summarizeWorkflowStates,
  type WorkflowStateKey,
} from "@/lib/workflows";

const workflowFilterItems = (counts: ReturnType<typeof summarizeWorkflowStates>) => [
  { label: "All", value: "all", count: counts.total },
  { label: "Active", value: "active", count: counts.active },
  { label: "Manual", value: "manual", count: counts.manual },
  { label: "Paused", value: "paused", count: counts.paused },
];

export default function WorkflowsPage() {
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState<"all" | WorkflowStateKey>("all");
  const [selectedWorkflowId, setSelectedWorkflowId] = useState("");
  const deferredSearch = useDeferredValue(search);

  const workflowsQuery = useQuery({
    queryKey: ["workflows", "jobs"],
    queryFn: () => getJobs({ limit: 200 }),
  });

  const workflows = useMemo(
    () => adaptWorkflowJobs(workflowsQuery.data || []),
    [workflowsQuery.data],
  );
  const workflowCounts = useMemo(
    () => summarizeWorkflowStates(workflows),
    [workflows],
  );

  const filteredWorkflows = useMemo(
    () =>
      workflows.filter(
        (item) =>
          (stateFilter === "all" || item.stateKey === stateFilter) &&
          matchesWorkflowSearch(item, deferredSearch),
      ),
    [deferredSearch, stateFilter, workflows],
  );

  useEffect(() => {
    if (filteredWorkflows.length === 0) {
      if (selectedWorkflowId) {
        startTransition(() => setSelectedWorkflowId(""));
      }
      return;
    }

    const selectedStillVisible = filteredWorkflows.some(
      (item) => item.id === selectedWorkflowId,
    );
    if (!selectedWorkflowId || !selectedStillVisible) {
      startTransition(() => setSelectedWorkflowId(filteredWorkflows[0].id));
    }
  }, [filteredWorkflows, selectedWorkflowId]);

  const selectedWorkflow =
    filteredWorkflows.find((item) => item.id === selectedWorkflowId) || null;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
      <div className="max-w-3xl">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Workflows</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Inspect automation lanes, cadence, and workflow readiness without
          returning to the legacy automation surface.
        </p>
      </div>

      <SectionShell
        title="Active workflows"
        description="Filter by lane state, then inspect cadence and retry posture in one place."
        actions={
          <button
            type="button"
            onClick={() => {
              void workflowsQuery.refetch();
            }}
            className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${workflowsQuery.isFetching ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <label className="relative block w-full max-w-md">
              <span className="sr-only">Search workflows</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                placeholder="Search workflows"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400"
              />
            </label>

            <FilterBar
              items={workflowFilterItems(workflowCounts)}
              value={stateFilter}
              onChange={(value) => setStateFilter(value as "all" | WorkflowStateKey)}
            />
          </div>

          <div className="divide-y divide-slate-200">
            {workflowsQuery.isLoading ? (
              <div className="py-8 text-sm text-slate-500">Loading workflow inventory…</div>
            ) : null}

            {!workflowsQuery.isLoading && filteredWorkflows.length === 0 ? (
              <div className="py-8 text-sm leading-6 text-slate-500">
                Tidak ada workflow yang cocok dengan filter saat ini. Coba ubah kata
                kunci atau state filter.
              </div>
            ) : null}

            {!workflowsQuery.isLoading
              ? filteredWorkflows.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() =>
                      startTransition(() => setSelectedWorkflowId(item.id))
                    }
                    className={`grid w-full gap-3 px-0 py-4 text-left md:grid-cols-[minmax(0,1fr)_auto] ${
                      item.id === selectedWorkflowId ? "bg-stone-50/70" : ""
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-slate-950">
                          {item.label}
                        </span>
                        <StatusPill tone={item.statusTone}>{item.statusLabel}</StatusPill>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-600">
                        {item.summary}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500 md:justify-end">
                      <span>{item.cadenceLabel}</span>
                      <span>{item.timeoutLabel}</span>
                      <span>{item.retryLabel}</span>
                    </div>
                  </button>
                ))
              : null}
          </div>
        </div>
      </SectionShell>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.7fr)_minmax(0,1.3fr)]">
        <SectionShell
          title="Workflow signals"
          description="Snapshot of the currently visible automation lanes."
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Active</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {workflowCounts.active}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Manual</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {workflowCounts.manual}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Paused</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {workflowCounts.paused}
              </p>
            </article>
          </div>
        </SectionShell>

        <SectionShell
          title={selectedWorkflow ? selectedWorkflow.label : "Select a workflow"}
          description={
            selectedWorkflow
              ? "Inspection summary for the selected workflow."
              : "Choose one workflow from the list to open cadence and retry details."
          }
        >
          {selectedWorkflow ? (
            <div className="grid gap-3 md:grid-cols-2">
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">State</p>
                <div className="mt-2">
                  <StatusPill tone={selectedWorkflow.statusTone}>
                    {selectedWorkflow.statusLabel}
                  </StatusPill>
                </div>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Type</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedWorkflow.typeLabel}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Cadence</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedWorkflow.cadenceLabel}
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {selectedWorkflow.cadenceDetail}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Timeout</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedWorkflow.timeoutLabel}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Retry policy</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedWorkflow.retryLabel}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Last run</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedWorkflow.lastRunLabel}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3 md:col-span-2">
                <p className="text-sm text-slate-500">Input posture</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedWorkflow.inputSummary}
                </p>
              </article>
            </div>
          ) : (
            <p className="text-sm leading-6 text-slate-500">
              Detail workflow akan tampil di sini setelah satu lane dipilih.
            </p>
          )}
        </SectionShell>
      </div>
    </div>
  );
}
