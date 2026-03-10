import {
  type ApprovalRequest,
  type Run,
  type SystemEvent,
  type SystemMetrics,
} from "@/lib/api";

const formatTimestamp = (value?: string): string => {
  if (!value) return "Belum ada";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("id-ID");
};

const humanizeToken = (value: string): string =>
  value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());

const clipText = (value: string, maxLength = 160): string => {
  const clean = String(value || "").trim();
  if (!clean) return "-";
  if (clean.length <= maxLength) return clean;
  return `${clean.slice(0, maxLength - 1)}…`;
};

export type IncidentSource = "approval" | "run" | "system";

export type IncidentItem = {
  id: string;
  source: IncidentSource;
  title: string;
  summary: string;
  statusLabel: string;
  statusTone: "info" | "warning" | "critical";
  createdLabel: string;
  sourceLabel: string;
  recoveryLabel: string;
  recoverySteps: string[];
  eventSummary: string;
  approvalId?: string;
  requestedPrefixes?: string[];
};

export type IncidentSignal = {
  id: string;
  title: string;
  detail: string;
  timestampLabel: string;
};

const buildApprovalIncident = (approval: ApprovalRequest): IncidentItem => {
  const requestedPrefixes = approval.command_allow_prefixes_requested || [];
  const requestSummary =
    approval.request_count > 0
      ? `${approval.request_count} approval item menunggu keputusan.`
      : "Approval menunggu keputusan operator.";

  return {
    id: `approval:${approval.approval_id}`,
    source: "approval",
    title: approval.summary || `${approval.job_id} membutuhkan approval`,
    summary: requestSummary,
    statusLabel: "Needs review",
    statusTone: "warning",
    createdLabel: formatTimestamp(approval.created_at),
    sourceLabel: `${humanizeToken(approval.job_type || approval.source || "approval")} · ${approval.job_id}`,
    recoveryLabel: "Review approval",
    recoverySteps: [
      `Baca ringkasan request dan prompt yang diajukan dari run ${approval.run_id}.`,
      requestedPrefixes.length > 0
        ? `Putuskan prefix command yang diminta: ${requestedPrefixes.join(", ")}.`
        : "Periksa provider atau MCP yang dibutuhkan sebelum memberi keputusan.",
      "Approve jika akses dan konteks aman, reject jika request terlalu luas atau belum lengkap.",
    ],
    eventSummary: clipText(approval.prompt, 220),
    approvalId: approval.approval_id,
    requestedPrefixes,
  };
};

const buildFailedRunIncident = (run: Run): IncidentItem => {
  const errorText = run.result?.error || "Run berakhir gagal tanpa pesan error rinci.";

  return {
    id: `run:${run.run_id}`,
    source: "run",
    title: `${run.job_id} gagal dieksekusi`,
    summary: clipText(errorText, 180),
    statusLabel: "Run failed",
    statusTone: "critical",
    createdLabel: formatTimestamp(run.finished_at || run.started_at || run.scheduled_at),
    sourceLabel: `${humanizeToken(run.status)} · ${run.job_id}`,
    recoveryLabel: "Inspect run",
    recoverySteps: [
      "Periksa input payload dan trace jika tersedia untuk memastikan penyebab gagal.",
      "Bandingkan attempt terakhir dengan retry policy workflow terkait.",
      "Setelah akar masalah jelas, jalankan ulang workflow atau eskalasi ke incident approval lane.",
    ],
    eventSummary: clipText(JSON.stringify(run.result?.output || {}, null, 2), 220),
  };
};

const buildSystemIncidents = (metrics: SystemMetrics): IncidentItem[] => {
  const items: IncidentItem[] = [];

  if (!metrics.api_online) {
    items.push({
      id: "system:api",
      source: "system",
      title: "API tidak merespons",
      summary: "Permintaan operator ke API gagal health check.",
      statusLabel: "Critical",
      statusTone: "critical",
      createdLabel: "Sekarang",
      sourceLabel: "System health",
      recoveryLabel: "Restore API",
      recoverySteps: [
        "Periksa health check API dan auth token yang sedang dipakai operator.",
        "Pastikan upstream service dan proxy route /api masih mengarah ke target yang benar.",
        "Tunda approval atau retry manual sampai health check kembali hijau.",
      ],
      eventSummary: "healthz/readyz tidak lolos.",
    });
  }

  if (!metrics.scheduler_online) {
    items.push({
      id: "system:scheduler",
      source: "system",
      title: "Scheduler offline",
      summary: "Lane otomatis tidak akan mengeluarkan run baru sampai scheduler kembali online.",
      statusLabel: "Warning",
      statusTone: "warning",
      createdLabel: "Sekarang",
      sourceLabel: "System scheduler",
      recoveryLabel: "Recover scheduler",
      recoverySteps: [
        "Konfirmasi scheduler process masih online dan heartbeat agen terbaru masih masuk.",
        "Pantau delayed queue untuk memastikan backlog tidak terus bertambah.",
        "Gunakan trigger manual hanya untuk workflow yang memang kritis.",
      ],
      eventSummary: `Queue depth ${metrics.queue_depth}, delayed ${metrics.delayed_count}.`,
    });
  }

  if (metrics.queue_depth >= 10 || metrics.delayed_count > 0) {
    items.push({
      id: "system:queue",
      source: "system",
      title: "Queue backlog perlu perhatian",
      summary: `Queue depth ${metrics.queue_depth} dengan delayed ${metrics.delayed_count}.`,
      statusLabel: metrics.queue_depth >= 25 ? "Critical" : "Warning",
      statusTone: metrics.queue_depth >= 25 ? "critical" : "warning",
      createdLabel: "Sekarang",
      sourceLabel: "Queue pressure",
      recoveryLabel: "Reduce pressure",
      recoverySteps: [
        "Prioritaskan incident approval dan failed run yang paling dekat dengan user impact.",
        "Periksa worker count dan beban run aktif sebelum men-trigger job baru.",
        "Jika backlog stabil, biarkan scheduler mengejar antrean tanpa menambah lane baru.",
      ],
      eventSummary: `Workers ${metrics.worker_count}, scheduler ${
        metrics.scheduler_online ? "online" : "offline"
      }.`,
    });
  }

  return items;
};

const summarizeEvent = (event: SystemEvent): IncidentSignal => {
  const typeLabel = humanizeToken(event.type || "system_event");
  const dataKeys = Object.keys(event.data || {});
  const detail =
    dataKeys.length > 0
      ? clipText(
          dataKeys
            .slice(0, 4)
            .map((key) => `${key}: ${String(event.data[key])}`)
            .join(" · "),
          180,
        )
      : "Tidak ada detail tambahan.";

  return {
    id: event.id,
    title: typeLabel,
    detail,
    timestampLabel: formatTimestamp(event.timestamp),
  };
};

export const adaptIncidents = (
  approvals: ApprovalRequest[],
  failedRuns: Run[],
  metrics: SystemMetrics,
): IncidentItem[] => [
  ...approvals.map(buildApprovalIncident),
  ...failedRuns.map(buildFailedRunIncident),
  ...buildSystemIncidents(metrics),
];

export const adaptIncidentSignals = (events: SystemEvent[]): IncidentSignal[] =>
  events.map(summarizeEvent);

export const summarizeIncidentCounts = (items: IncidentItem[]) => ({
  total: items.length,
  approvals: items.filter((item) => item.source === "approval").length,
  runs: items.filter((item) => item.source === "run").length,
  system: items.filter((item) => item.source === "system").length,
});

export const matchesIncidentSearch = (item: IncidentItem, search: string): boolean => {
  const query = search.trim().toLowerCase();
  if (!query) return true;

  return [
    item.title,
    item.summary,
    item.sourceLabel,
    item.statusLabel,
    item.eventSummary,
    ...(item.requestedPrefixes || []),
  ].some((field) => field.toLowerCase().includes(query));
};
