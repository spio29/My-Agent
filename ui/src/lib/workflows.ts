import { type JobSpec, type Run } from "@/lib/api";

const humanizeToken = (value: string): string =>
  value
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());

const formatTimestamp = (value?: string): string => {
  if (!value) return "Belum ada";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("id-ID");
};

const formatDuration = (valueMs?: number): string => {
  if (!valueMs) return "-";
  if (valueMs < 1000) return `${valueMs} ms`;
  if (valueMs < 60_000) return `${(valueMs / 1000).toFixed(1)} s`;
  return `${(valueMs / 60_000).toFixed(1)} min`;
};

const formatInterval = (seconds: number): string => {
  if (seconds < 60) return `${seconds} detik`;
  if (seconds % 3600 === 0) return `${seconds / 3600} jam`;
  if (seconds % 60 === 0) return `${seconds / 60} menit`;

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes} menit ${remainingSeconds} detik`;
};

const formatSchedule = (job: JobSpec): { label: string; detail: string } => {
  if (job.schedule?.interval_sec) {
    return {
      label: `Setiap ${formatInterval(job.schedule.interval_sec)}`,
      detail: `Interval ${job.schedule.interval_sec} detik`,
    };
  }

  if (job.schedule?.cron) {
    return {
      label: "Jadwal cron",
      detail: job.schedule.cron,
    };
  }

  return {
    label: "Manual",
    detail: "Tidak ada jadwal otomatis",
  };
};

const formatRetryPolicy = (job: JobSpec): string => {
  const retryCount = job.retry_policy?.max_retry ?? 0;
  if (retryCount <= 0) return "Tanpa retry";

  const backoff = Array.isArray(job.retry_policy?.backoff_sec)
    ? job.retry_policy.backoff_sec.filter((value) => Number.isFinite(value))
    : [];
  if (backoff.length === 0) return `${retryCount} retry`;

  return `${retryCount} retry · ${backoff.join(", ")} detik`;
};

const summarizeInputs = (job: JobSpec): string => {
  const keys = Object.keys(job.inputs || {});
  if (keys.length === 0) return "Tanpa input tambahan";
  if (keys.length <= 3) return `Input: ${keys.join(", ")}`;
  return `Input: ${keys.slice(0, 3).join(", ")} +${keys.length - 3}`;
};

export type WorkflowStateKey = "active" | "manual" | "paused";

export type WorkflowItem = {
  id: string;
  label: string;
  statusLabel: string;
  statusTone: "success" | "info" | "warning";
  stateKey: WorkflowStateKey;
  cadenceLabel: string;
  cadenceDetail: string;
  timeoutLabel: string;
  retryLabel: string;
  lastRunLabel: string;
  typeLabel: string;
  summary: string;
  inputSummary: string;
};

export const adaptWorkflowJobs = (jobs: JobSpec[]): WorkflowItem[] =>
  jobs.map((job) => {
    const schedule = formatSchedule(job);
    const isEnabled = job.enabled !== false;
    const hasAutomation = Boolean(job.schedule?.cron || job.schedule?.interval_sec);
    const stateKey: WorkflowStateKey = !isEnabled ? "paused" : hasAutomation ? "active" : "manual";

    return {
      id: job.job_id,
      label: humanizeToken(job.job_id),
      statusLabel: stateKey === "active" ? "Active" : stateKey === "manual" ? "Manual" : "Paused",
      statusTone: stateKey === "active" ? "success" : stateKey === "manual" ? "info" : "warning",
      stateKey,
      cadenceLabel: schedule.label,
      cadenceDetail: schedule.detail,
      timeoutLabel: formatDuration(job.timeout_ms),
      retryLabel: formatRetryPolicy(job),
      lastRunLabel: formatTimestamp(job.last_run_time),
      typeLabel: humanizeToken(job.type || "generic"),
      summary: `${humanizeToken(job.type || "Workflow")} · ${schedule.label}`,
      inputSummary: summarizeInputs(job),
    };
  });

export const summarizeWorkflowStates = (items: WorkflowItem[]) => ({
  total: items.length,
  active: items.filter((item) => item.stateKey === "active").length,
  manual: items.filter((item) => item.stateKey === "manual").length,
  paused: items.filter((item) => item.stateKey === "paused").length,
});

export const matchesWorkflowSearch = (item: WorkflowItem, search: string): boolean => {
  const query = search.trim().toLowerCase();
  if (!query) return true;

  return [
    item.id,
    item.label,
    item.typeLabel,
    item.summary,
    item.inputSummary,
    item.cadenceLabel,
    item.cadenceDetail,
  ].some((field) => field.toLowerCase().includes(query));
};

export type RunRow = {
  id: string;
  workflowId: string;
  statusLabel: string;
  statusTone: "neutral" | "info" | "success" | "critical";
  scheduledLabel: string;
  startedLabel: string;
  finishedLabel: string;
  durationLabel: string;
  attemptLabel: string;
  traceId: string;
  summary: string;
  errorText: string;
  inputsText: string;
  outputText: string;
};

export const adaptRunRows = (runs: Run[]): RunRow[] =>
  runs.map((run) => {
    const statusTone =
      run.status === "success"
        ? "success"
        : run.status === "failed"
          ? "critical"
          : run.status === "running"
            ? "info"
            : "neutral";

    const resultSummary = run.result?.error
      ? run.result.error
      : run.result?.success
        ? "Run selesai tanpa error."
        : "Run masih menunggu hasil akhir.";

    return {
      id: run.run_id,
      workflowId: run.job_id,
      statusLabel: humanizeToken(run.status),
      statusTone,
      scheduledLabel: formatTimestamp(run.scheduled_at),
      startedLabel: formatTimestamp(run.started_at),
      finishedLabel: formatTimestamp(run.finished_at),
      durationLabel: formatDuration(run.result?.duration_ms),
      attemptLabel: `Attempt ${run.attempt}`,
      traceId: run.trace_id || "-",
      summary: resultSummary,
      errorText: run.result?.error || "Tidak ada error",
      inputsText: JSON.stringify(run.inputs || {}, null, 2),
      outputText: JSON.stringify(run.result?.output || {}, null, 2),
    };
  });

export const summarizeRunStates = (rows: RunRow[]) => ({
  total: rows.length,
  queued: rows.filter((row) => row.statusLabel === "Queued").length,
  running: rows.filter((row) => row.statusLabel === "Running").length,
  success: rows.filter((row) => row.statusLabel === "Success").length,
  failed: rows.filter((row) => row.statusLabel === "Failed").length,
});
