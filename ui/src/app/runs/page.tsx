"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";

import FilterBar from "@/components/operator/filter-bar";
import SectionShell from "@/components/operator/section-shell";
import StatusPill from "@/components/operator/status-pill";
import { getRuns } from "@/lib/api";
import { adaptRunRows, summarizeRunStates } from "@/lib/workflows";

const runFilterItems = (counts: ReturnType<typeof summarizeRunStates>) => [
  { label: "All", value: "all", count: counts.total },
  { label: "Queued", value: "queued", count: counts.queued },
  { label: "Running", value: "running", count: counts.running },
  { label: "Success", value: "success", count: counts.success },
  { label: "Failed", value: "failed", count: counts.failed },
];

export default function RunsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedRunId, setSelectedRunId] = useState("");
  const deferredSearch = useDeferredValue(search);

  const runsQuery = useQuery({
    queryKey: ["operator-runs", statusFilter, deferredSearch],
    queryFn: () =>
      getRuns({
        limit: 60,
        status: statusFilter !== "all" ? statusFilter : undefined,
        search: deferredSearch.trim() || undefined,
      }),
  });

  const runRows = useMemo(() => adaptRunRows(runsQuery.data || []), [runsQuery.data]);
  const runCounts = useMemo(() => summarizeRunStates(runRows), [runRows]);

  useEffect(() => {
    if (runRows.length === 0) {
      if (selectedRunId) {
        startTransition(() => setSelectedRunId(""));
      }
      return;
    }

    const selectedStillVisible = runRows.some((row) => row.id === selectedRunId);
    if (!selectedRunId || !selectedStillVisible) {
      startTransition(() => setSelectedRunId(runRows[0].id));
    }
  }, [runRows, selectedRunId]);

  const selectedRun = runRows.find((row) => row.id === selectedRunId) || null;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
      <div className="max-w-3xl">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Runs</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Review queue output, inspect failed attempts, and keep execution history in
          the same operator shell as portfolio workflows.
        </p>
      </div>

      <SectionShell
        title="Execution queue"
        description="Search current runs, narrow by status, and open the run detail without leaving the page."
        actions={
          <button
            type="button"
            onClick={() => {
              void runsQuery.refetch();
            }}
            className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${runsQuery.isFetching ? "animate-spin" : ""}`}
            />
            Refresh
          </button>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <label className="relative block w-full max-w-md">
              <span className="sr-only">Search runs</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                placeholder="Search runs"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400"
              />
            </label>

            <FilterBar
              items={runFilterItems(runCounts)}
              value={statusFilter}
              onChange={setStatusFilter}
            />
          </div>

          {runsQuery.isLoading ? (
            <div className="py-8 text-sm text-slate-500">Loading run history…</div>
          ) : null}

          {!runsQuery.isLoading && runRows.length === 0 ? (
            <div className="py-8 text-sm leading-6 text-slate-500">
              Tidak ada run yang cocok dengan pencarian sekarang. Ubah kata kunci atau
              pilih status lain untuk melihat antrean yang tersedia.
            </div>
          ) : null}

          {!runsQuery.isLoading && runRows.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
                <thead className="bg-stone-50 text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-medium">Run</th>
                    <th className="px-4 py-3 font-medium">Workflow</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Scheduled</th>
                    <th className="px-4 py-3 font-medium">Duration</th>
                    <th className="px-4 py-3 font-medium">Attempt</th>
                    <th className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {runRows.map((row) => (
                    <tr
                      key={row.id}
                      className={row.id === selectedRunId ? "bg-stone-50/80" : ""}
                    >
                      <td className="px-4 py-3 font-medium text-slate-950">{row.id}</td>
                      <td className="px-4 py-3 text-slate-700">{row.workflowId}</td>
                      <td className="px-4 py-3">
                        <StatusPill tone={row.statusTone}>{row.statusLabel}</StatusPill>
                      </td>
                      <td className="px-4 py-3 text-slate-700">{row.scheduledLabel}</td>
                      <td className="px-4 py-3 text-slate-700">{row.durationLabel}</td>
                      <td className="px-4 py-3 text-slate-700">{row.attemptLabel}</td>
                      <td className="px-4 py-3">
                        <button
                          type="button"
                          onClick={() =>
                            startTransition(() => setSelectedRunId(row.id))
                          }
                          className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      </SectionShell>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.55fr)_minmax(0,1.45fr)]">
        <SectionShell
          title="Run signals"
          description="Snapshot of the visible execution queue."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Running</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {runCounts.running}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Failed</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {runCounts.failed}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Queued</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {runCounts.queued}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Success</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {runCounts.success}
              </p>
            </article>
          </div>
        </SectionShell>

        <SectionShell
          title={selectedRun ? selectedRun.id : "Select a run"}
          description={
            selectedRun
              ? "Inspection summary for the selected execution."
              : "Choose one run to inspect timing, trace, and payload output."
          }
        >
          {selectedRun ? (
            <div className="flex flex-col gap-4">
              <div className="grid gap-3 md:grid-cols-2">
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Status</p>
                  <div className="mt-2">
                    <StatusPill tone={selectedRun.statusTone}>
                      {selectedRun.statusLabel}
                    </StatusPill>
                  </div>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Workflow</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {selectedRun.workflowId}
                  </p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Scheduled</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {selectedRun.scheduledLabel}
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Started: {selectedRun.startedLabel}
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Finished: {selectedRun.finishedLabel}
                  </p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Trace</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {selectedRun.traceId}
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    {selectedRun.attemptLabel} · {selectedRun.durationLabel}
                  </p>
                </article>
              </div>

              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Summary</p>
                <p className="mt-1 text-sm font-medium text-slate-900">
                  {selectedRun.summary}
                </p>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  {selectedRun.errorText}
                </p>
              </article>

              <div className="grid gap-4 xl:grid-cols-2">
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Input payload</p>
                  <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-700">
                    {selectedRun.inputsText}
                  </pre>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Output payload</p>
                  <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-md border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-700">
                    {selectedRun.outputText}
                  </pre>
                </article>
              </div>
            </div>
          ) : (
            <p className="text-sm leading-6 text-slate-500">
              Detail run akan tampil di sini setelah satu baris dipilih.
            </p>
          )}
        </SectionShell>
      </div>
    </div>
  );
}
