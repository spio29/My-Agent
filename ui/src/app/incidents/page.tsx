"use client";

import { startTransition, useDeferredValue, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

import FilterBar from "@/components/operator/filter-bar";
import SectionShell from "@/components/operator/section-shell";
import StatusPill from "@/components/operator/status-pill";
import {
  approveApprovalRequest,
  getApprovalRequests,
  getEvents,
  getRuns,
  getSystemMetrics,
  rejectApprovalRequest,
} from "@/lib/api";
import {
  adaptIncidents,
  adaptIncidentSignals,
  matchesIncidentSearch,
  summarizeIncidentCounts,
  type IncidentSource,
} from "@/lib/incidents";

const incidentFilterItems = (counts: ReturnType<typeof summarizeIncidentCounts>) => [
  { label: "All", value: "all", count: counts.total },
  { label: "Approval", value: "approval", count: counts.approvals },
  { label: "Failed runs", value: "run", count: counts.runs },
  { label: "System", value: "system", count: counts.system },
];

export default function IncidentsPage() {
  const [search, setSearch] = useState("");
  const [sourceFilter, setSourceFilter] = useState<"all" | IncidentSource>("all");
  const [selectedIncidentId, setSelectedIncidentId] = useState("");
  const [isDecisionPending, setIsDecisionPending] = useState(false);
  const deferredSearch = useDeferredValue(search);

  const approvalsQuery = useQuery({
    queryKey: ["incidents", "approvals"],
    queryFn: () => getApprovalRequests({ status: "pending", limit: 20 }),
  });
  const failedRunsQuery = useQuery({
    queryKey: ["incidents", "failed-runs"],
    queryFn: () => getRuns({ status: "failed", limit: 12 }),
  });
  const metricsQuery = useQuery({
    queryKey: ["incidents", "metrics"],
    queryFn: () => getSystemMetrics(),
  });
  const eventsQuery = useQuery({
    queryKey: ["incidents", "signals"],
    queryFn: () => getEvents({ limit: 10 }),
  });

  const incidents = useMemo(
    () =>
      adaptIncidents(
        approvalsQuery.data || [],
        failedRunsQuery.data || [],
        metricsQuery.data || {
          queue_depth: 0,
          delayed_count: 0,
          worker_count: 0,
          scheduler_online: true,
          redis_online: true,
          api_online: true,
        },
      ),
    [approvalsQuery.data, failedRunsQuery.data, metricsQuery.data],
  );
  const incidentCounts = useMemo(() => summarizeIncidentCounts(incidents), [incidents]);
  const recentSignals = useMemo(
    () => adaptIncidentSignals(eventsQuery.data || []),
    [eventsQuery.data],
  );

  const filteredIncidents = useMemo(
    () =>
      incidents.filter(
        (item) =>
          (sourceFilter === "all" || item.source === sourceFilter) &&
          matchesIncidentSearch(item, deferredSearch),
      ),
    [deferredSearch, incidents, sourceFilter],
  );

  useEffect(() => {
    if (filteredIncidents.length === 0) {
      if (selectedIncidentId) {
        startTransition(() => setSelectedIncidentId(""));
      }
      return;
    }

    const selectedStillVisible = filteredIncidents.some(
      (item) => item.id === selectedIncidentId,
    );
    if (!selectedIncidentId || !selectedStillVisible) {
      startTransition(() => setSelectedIncidentId(filteredIncidents[0].id));
    }
  }, [filteredIncidents, selectedIncidentId]);

  const selectedIncident =
    filteredIncidents.find((item) => item.id === selectedIncidentId) || null;

  const refreshAll = async () => {
    await Promise.all([
      approvalsQuery.refetch(),
      failedRunsQuery.refetch(),
      metricsQuery.refetch(),
      eventsQuery.refetch(),
    ]);
  };

  const handleApprovalDecision = async (decision: "approve" | "reject") => {
    if (!selectedIncident?.approvalId) return;

    setIsDecisionPending(true);
    try {
      const response =
        decision === "approve"
          ? await approveApprovalRequest(selectedIncident.approvalId, {
              decision_by: "operator",
              decision_note: "Reviewed from incidents workspace",
            })
          : await rejectApprovalRequest(selectedIncident.approvalId, {
              decision_by: "operator",
              decision_note: "Rejected from incidents workspace",
            });

      if (response) {
        toast.success(
          decision === "approve"
            ? "Approval request disetujui."
            : "Approval request ditolak.",
        );
        await refreshAll();
      }
    } finally {
      setIsDecisionPending(false);
    }
  };

  const pendingPrefixSummary = (approvalsQuery.data || [])
    .flatMap((item) => item.command_allow_prefixes_requested || [])
    .slice(0, 6);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
      <div className="max-w-3xl">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Incidents</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Review approval queue, failed execution pressure, and system signals in one
          operator workspace before deciding the next follow-up.
        </p>
      </div>

      <SectionShell
        title="Incident queue"
        description="Filter open incidents by source, then inspect one incident at a time without leaving the page."
        actions={
          <button
            type="button"
            onClick={() => {
              void refreshAll();
            }}
            className="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
          >
            <RefreshCw
              className={`h-4 w-4 ${
                approvalsQuery.isFetching ||
                failedRunsQuery.isFetching ||
                metricsQuery.isFetching ||
                eventsQuery.isFetching
                  ? "animate-spin"
                  : ""
              }`}
            />
            Refresh
          </button>
        }
      >
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <label className="relative block w-full max-w-md">
              <span className="sr-only">Search incidents</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                placeholder="Search incidents"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400"
              />
            </label>

            <FilterBar
              items={incidentFilterItems(incidentCounts)}
              value={sourceFilter}
              onChange={(value) => setSourceFilter(value as "all" | IncidentSource)}
            />
          </div>

          <div className="divide-y divide-slate-200">
            {approvalsQuery.isLoading ||
            failedRunsQuery.isLoading ||
            metricsQuery.isLoading ? (
              <div className="py-8 text-sm text-slate-500">Loading incident queue…</div>
            ) : null}

            {!approvalsQuery.isLoading &&
            !failedRunsQuery.isLoading &&
            !metricsQuery.isLoading &&
            filteredIncidents.length === 0 ? (
              <div className="py-8 text-sm leading-6 text-slate-500">
                Tidak ada incident yang cocok dengan filter saat ini.
              </div>
            ) : null}

            {filteredIncidents.map((incident) => (
              <button
                key={incident.id}
                type="button"
                onClick={() => startTransition(() => setSelectedIncidentId(incident.id))}
                className={`grid w-full gap-3 px-0 py-4 text-left md:grid-cols-[minmax(0,1fr)_auto] ${
                  incident.id === selectedIncidentId ? "bg-stone-50/70" : ""
                }`}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-950">
                      {incident.title}
                    </span>
                    <StatusPill tone={incident.statusTone}>
                      {incident.statusLabel}
                    </StatusPill>
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {incident.summary}
                  </p>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500 md:justify-end">
                  <span>{incident.sourceLabel}</span>
                  <span>{incident.createdLabel}</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      </SectionShell>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <SectionShell
          title="Recovery"
          description={
            selectedIncident
              ? "Recommended operator follow-up for the selected incident."
              : "Select one incident to open the recovery recommendation."
          }
        >
          {selectedIncident ? (
            <div className="flex flex-col gap-4">
              <div className="grid gap-3 md:grid-cols-2">
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Incident</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {selectedIncident.title}
                  </p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Action lane</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {selectedIncident.recoveryLabel}
                  </p>
                </article>
              </div>

              <div className="space-y-3">
                {selectedIncident.recoverySteps.map((step) => (
                  <article
                    key={step}
                    className="rounded-lg border border-slate-200 bg-white px-4 py-3"
                  >
                    <p className="text-sm leading-6 text-slate-700">{step}</p>
                  </article>
                ))}
              </div>

              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Context</p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {selectedIncident.eventSummary}
                </p>
              </article>

              {selectedIncident.approvalId ? (
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={isDecisionPending}
                    onClick={() => {
                      void handleApprovalDecision("approve");
                    }}
                    className="rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={isDecisionPending}
                    onClick={() => {
                      void handleApprovalDecision("reject");
                    }}
                    className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Reject
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm leading-6 text-slate-500">
              Recovery recommendation akan tampil di sini setelah satu incident dipilih.
            </p>
          )}
        </SectionShell>

        <div className="flex flex-col gap-5">
          <SectionShell
            title="Approval lane"
            description="Live summary of approval pressure and requested operator scopes."
          >
            <div className="grid gap-3">
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Pending approvals</p>
                <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                  {(approvalsQuery.data || []).length}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Requested prefixes</p>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  {pendingPrefixSummary.length > 0
                    ? pendingPrefixSummary.join(", ")
                    : "Tidak ada prefix command tambahan yang sedang diminta."}
                </p>
              </article>
              <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                <p className="text-sm text-slate-500">Failed runs</p>
                <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                  {(failedRunsQuery.data || []).length}
                </p>
              </article>
            </div>
          </SectionShell>

          <SectionShell
            title="Recent signals"
            description="Recent events that help explain why the queue needs attention."
          >
            <div className="divide-y divide-slate-200">
              {recentSignals.length === 0 ? (
                <div className="py-4 text-sm text-slate-500">
                  Belum ada sinyal terbaru yang bisa ditampilkan.
                </div>
              ) : (
                recentSignals.map((signal) => (
                  <article key={signal.id} className="py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h4 className="text-sm font-semibold text-slate-950">
                        {signal.title}
                      </h4>
                      <span className="text-sm text-slate-500">
                        {signal.timestampLabel}
                      </span>
                    </div>
                    <p className="mt-1 text-sm leading-6 text-slate-600">
                      {signal.detail}
                    </p>
                  </article>
                ))
              )}
            </div>
          </SectionShell>
        </div>
      </div>
    </div>
  );
}
