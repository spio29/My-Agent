import { toast } from "sonner";

const DEFAULT_API_BASE = "/api";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE;
const API_AUTH_STORAGE_KEY = "spio_api_token";
const API_AUTH_HEADER = process.env.NEXT_PUBLIC_API_AUTH_HEADER || "Authorization";
const API_AUTH_SCHEME = process.env.NEXT_PUBLIC_API_AUTH_SCHEME || "Bearer";
const API_AUTH_TOKEN_ENV = process.env.NEXT_PUBLIC_API_TOKEN || "";

const resolveApiBase = (): string => {
  const configured = String(API_BASE || "").trim() || DEFAULT_API_BASE;
  return configured.startsWith("/") ? configured : configured.replace(/\/+$/, "");
};

export interface JobSpec {
  job_id: string;
  type: string;
  enabled?: boolean;
  schedule?: {
    cron?: string;
    interval_sec?: number;
  };
  timeout_ms: number;
  retry_policy: {
    max_retry: number;
    backoff_sec: number[];
  };
  inputs: Record<string, unknown>;
  last_run_time?: string;
}

export interface JobSpecVersion {
  version_id: string;
  job_id: string;
  created_at: string;
  source: string;
  actor: string;
  note: string;
  spec: Record<string, unknown>;
}

export interface JobRollbackResult {
  job_id: string;
  status: "rolled_back";
  rolled_back_to_version_id: string;
  enabled: boolean;
  spec: Record<string, unknown>;
}

export interface Run {
  run_id: string;
  job_id: string;
  status: "queued" | "running" | "success" | "failed";
  attempt: number;
  scheduled_at: string;
  started_at?: string;
  finished_at?: string;
  inputs?: Record<string, unknown>;
  result?: {
    success: boolean;
    output?: Record<string, unknown>;
    error?: string;
    duration_ms?: number;
  };
  trace_id?: string;
}

export type RunStatus = Run["status"];

export interface Connector {
  channel: string;
  account_id: string;
  status: "online" | "offline" | "degraded";
  last_heartbeat_at?: string;
  reconnect_count?: number;
  last_error?: string;
}

export interface TelegramConnectorAccount {
  account_id: string;
  enabled: boolean;
  has_bot_token: boolean;
  bot_token_masked?: string;
  allowed_chat_ids: string[];
  use_ai: boolean;
  force_rule_based: boolean;
  run_immediately: boolean;
  wait_seconds: number;
  timezone: string;
  default_channel: string;
  default_account_id: string;
  default_branch_id?: string;
  capture_inbound_text?: boolean;
  inbound_auto_followup?: boolean;
  inbound_followup_template?: string;
  created_at?: string;
  updated_at?: string;
}

export interface TelegramConnectorAccountUpsertRequest {
  bot_token?: string;
  allowed_chat_ids: string[];
  enabled: boolean;
  use_ai: boolean;
  force_rule_based: boolean;
  run_immediately: boolean;
  wait_seconds: number;
  timezone: string;
  default_channel: string;
  default_account_id: string;
  default_branch_id?: string;
  capture_inbound_text?: boolean;
  inbound_auto_followup?: boolean;
  inbound_followup_template?: string;
}

export interface McpIntegrationServer {
  server_id: string;
  enabled: boolean;
  transport: "stdio" | "http" | "sse";
  description: string;
  command: string;
  args: string[];
  url: string;
  headers: Record<string, string>;
  env: Record<string, string>;
  has_auth_token: boolean;
  auth_token_masked?: string;
  timeout_sec: number;
  created_at?: string;
  updated_at?: string;
}

export interface McpIntegrationServerUpsertRequest {
  enabled: boolean;
  transport: "stdio" | "http" | "sse";
  description: string;
  command: string;
  args: string[];
  url: string;
  headers: Record<string, string>;
  env: Record<string, string>;
  auth_token?: string;
  timeout_sec: number;
}

export interface IntegrationAccount {
  provider: string;
  account_id: string;
  enabled: boolean;
  has_secret: boolean;
  secret_masked?: string;
  config: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface IntegrationAccountUpsertRequest {
  enabled: boolean;
  secret?: string;
  config: Record<string, unknown>;
}

export interface IntegrationProviderTemplate {
  provider: string;
  label: string;
  description: string;
  auth_hint: string;
  default_account_id: string;
  default_enabled: boolean;
  default_config: Record<string, unknown>;
}

export interface McpServerTemplate {
  template_id: string;
  server_id: string;
  label: string;
  description: string;
  transport: "stdio" | "http" | "sse";
  command: string;
  args: string[];
  url: string;
  headers: Record<string, string>;
  env: Record<string, string>;
  timeout_sec: number;
  default_enabled: boolean;
}

export interface IntegrationsCatalog {
  providers: IntegrationProviderTemplate[];
  mcp_servers: McpServerTemplate[];
}

export interface IntegrationsBootstrapRequest {
  provider_ids?: string[];
  mcp_template_ids?: string[];
  account_id?: string;
  overwrite?: boolean;
}

export interface IntegrationsBootstrapResponse {
  account_id: string;
  overwrite: boolean;
  providers_created: string[];
  providers_updated: string[];
  providers_skipped: string[];
  mcp_created: string[];
  mcp_updated: string[];
  mcp_skipped: string[];
}

export interface Agent {
  id: string;
  type?: string;
  status: "online" | "offline";
  last_heartbeat: string;
  active_sessions?: number;
  pool?: string;
  version?: string;
}

export interface AgentMemoryFailure {
  at: string;
  signature: string;
  error: string;
}

export interface AgentMemoryEpisodic {
  timestamp: string;
  type: string;
  description: string;
  constext: Record<string, unknown>;
}

export interface AgentMemorySummary {
  agent_key: string;
  total_runs: number;
  success_runs: number;
  failed_runs: number;
  success_rate: number;
  last_error: string;
  last_summary: string;
  avoid_signatures: string[];
  top_failure_signatures: string[];
  recent_failures: AgentMemoryFailure[];
  episodic_events?: AgentMemoryEpisodic[];
  tags?: string[];
  updated_at: string;
}

export interface AgentMemoryResetResponse {
  agent_key: string;
  deleted: boolean;
  status: "cleared" | "not_found";
}

export interface SystemMetrics {
  queue_depth: number;
  delayed_count: number;
  worker_count: number;
  scheduler_online: boolean;
  redis_online: boolean;
  api_online: boolean;
}

export interface SystemEvent {
  id: string;
  type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

export interface AuditLog {
  id: string;
  timestamp: string;
  method: string;
  path: string;
  status_code: number;
  outcome: "success" | "error" | "denied";
  required_role: string;
  actor_role: string;
  actor_subject: string;
  auth_enabled: boolean;
  query: string;
  detail: string;
  client_ip: string;
}

export interface PlannerExecutionResult {
  job_id: string;
  type: string;
  create_status: "created" | "updated" | "error";
  run_id?: string;
  queue_status?: string;
  run_status?: "queued" | "running" | "success" | "failed";
  result_success?: boolean;
  result_error?: string;
}

export interface PlannerExecuteResponse {
  planner_source: "rule_based" | "smolagents";
  summary: string;
  assumptions: string[];
  warnings: string[];
  results: PlannerExecutionResult[];
}

export interface PlannerExecuteRequest {
  prompt: string;
  use_ai?: boolean;
  force_rule_based?: boolean;
  ai_provider?: string;
  ai_account_id?: string;
  openai_account_id?: string;
  run_immediately?: boolean;
  wait_seconds?: number;
  timezone?: string;
}

export interface AgentWorkflowAutomationRequest {
  job_id: string;
  prompt: string;
  interval_sec?: number;
  cron?: string;
  enabled?: boolean;
  timezone?: string;
  default_channel?: string;
  default_account_id?: string;
  flow_group?: string;
  flow_max_active_runs?: number;
  require_approval_for_missing?: boolean;
  allow_overlap?: boolean;
  pressure_priority?: "critical" | "normal" | "low";
  dispatch_jitter_sec?: number;
  failure_threshold?: number;
  failure_cooldown_sec?: number;
  failure_cooldown_max_sec?: number;
  failure_memory_enabled?: boolean;
  command_allow_prefixes?: string[];
  allow_sensitive_commands?: boolean;
  timeout_ms?: number;
  max_retry?: number;
  backoff_sec?: number[];
}

export interface AgentWorkflowAutomationJob extends JobSpec {
  status?: "created" | "updated";
}

export interface ApprovalRequest {
  approval_id: string;
  status: "pending" | "approved" | "rejected";
  source: string;
  run_id: string;
  job_id: string;
  job_type: string;
  prompt: string;
  summary: string;
  request_count: number;
  approval_requests: Record<string, unknown>[];
  available_providers: Record<string, unknown>;
  available_mcp_servers: unknown[];
  command_allow_prefixes_requested: string[];
  command_allow_prefixes_rejected: string[];
  created_at: string;
  updated_at: string;
  decided_at?: string;
  decision_by?: string;
  decision_note?: string;
}

export type ApprovalStatus = ApprovalRequest["status"];

export interface Experiment {
  experiment_id: string;
  name: string;
  description: string;
  job_id: string;
  hypothesis: string;
  variant_a_name: string;
  variant_b_name: string;
  variant_a_prompt: string;
  variant_b_prompt: string;
  traffic_split_b: number;
  enabled: boolean;
  tags: string[];
  owner: string;
  notes: string;
  created_at?: string;
  updated_at?: string;
  last_variant?: string;
  last_variant_name?: string;
  last_variant_bucket?: number;
  last_variant_run_at?: string;
}

export interface ExperimentUpsertRequest {
  name: string;
  description?: string;
  job_id?: string;
  hypothesis?: string;
  variant_a_name?: string;
  variant_b_name?: string;
  variant_a_prompt: string;
  variant_b_prompt: string;
  traffic_split_b?: number;
  enabled?: boolean;
  tags?: string[];
  owner?: string;
  notes?: string;
}

export interface Trigger {
  trigger_id: string;
  name: string;
  job_id: string;
  channel: string;
  description: string;
  enabled: boolean;
  default_payload: Record<string, unknown>;
  secret_present: boolean;
  requires_approval?: boolean;
  created_at?: string;
  updated_at?: string;
  last_fired_run_id?: string;
  last_fired_at?: string;
}

export interface TriggerUpsertRequest {
  name: string;
  job_id: string;
  channel: string;
  description?: string;
  enabled?: boolean;
  default_payload?: Record<string, unknown>;
  secret?: string;
  requires_approval?: boolean;
}

export interface TriggerFireResponse {
  trigger_id: string;
  job_id: string;
  message_id: string;
  run_id: string;
  channel: string;
  source: string;
}

export interface RateLimitConfig {
  max_runs: number;
  window_sec: number;
}

export interface Skill {
  skill_id: string;
  name: string;
  description: string;
  job_type: string;
  version: string;
  runbook: string;
  source: string;
  default_inputs: Record<string, unknown>;
  command_allow_prefixes: string[];
  allowed_channels: string[];
  tags: string[];
  tool_allowlist?: string[];
  required_secrets?: string[];
  rate_limit?: RateLimitConfig;
  allow_sensitive_commands: boolean;
  require_approval: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SkillSpecRequest {
  name: string;
  description?: string;
  job_type: string;
  version?: string;
  runbook?: string;
  source?: string;
  default_inputs?: Record<string, unknown>;
  command_allow_prefixes?: string[];
  allowed_channels?: string[];
  tags?: string[];
  tool_allowlist?: string[];
  required_secrets?: string[];
  rate_limit?: RateLimitConfig;
  allow_sensitive_commands?: boolean;
  require_approval?: boolean;
}

const handleApiError = <T>(error: unknown, message: string, fallback: T): T => {
  console.error(`${message}:`, error);
  toast.error(message);
  return fallback;
};

const getStoredApiToken = (): string => {
  if (typeof window === "undefined") return "";
  try {
    return (window.localStorage.getItem(API_AUTH_STORAGE_KEY) || "").trim();
  } catch {
    return "";
  }
};

const resolveApiToken = (): string => {
  const token = getStoredApiToken();
  if (token) return token;
  return String(API_AUTH_TOKEN_ENV || "").trim();
};

const buildAuthHeaders = (): HeadersInit => {
  const token = resolveApiToken();
  if (!token) return {};

  if (API_AUTH_HEADER.toLowerCase() === "authorization") {
    const scheme = String(API_AUTH_SCHEME || "").trim();
    return {
      [API_AUTH_HEADER]: scheme ? `${scheme} ${token}` : token,
    };
  }

  return {
    [API_AUTH_HEADER]: token,
  };
};

const buildHeaders = (withJsonContentType: boolean): HeadersInit => {
  const headers: Record<string, string> = {};
  if (withJsonContentType) {
    headers["Content-Type"] = "application/json";
  }

  const authHeaders = buildAuthHeaders() as Record<string, string>;
  for (const [key, value] of Object.entries(authHeaders)) {
    headers[key] = value;
  }

  return headers;
};

export const setApiAuthToken = (token: string): void => {
  if (typeof window === "undefined") return;
  try {
    const value = String(token || "").trim();
    if (!value) {
      window.localStorage.removeItem(API_AUTH_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(API_AUTH_STORAGE_KEY, value);
  } catch {
    // no-op
  }
};

export const clearApiAuthToken = (): void => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(API_AUTH_STORAGE_KEY);
  } catch {
    // no-op
  }
};

export const getApiAuthToken = (): string => resolveApiToken();

const getJson = async <T>(path: string): Promise<T> => {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    headers: buildHeaders(false),
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
};

const send = async <T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown): Promise<T> => {
  const response = await fetch(`${resolveApiBase()}${path}`, {
    method,
    headers: buildHeaders(Boolean(body)),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
};

export const getJobs = async (params?: {
  search?: string;
  enabled?: boolean;
  limit?: number;
  offset?: number;
}): Promise<JobSpec[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (params?.search) queryParams.append("search", params.search);
    if (typeof params?.enabled === "boolean") queryParams.append("enabled", params.enabled ? "true" : "false");
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (typeof params?.offset === "number" && params.offset >= 0) queryParams.append("offset", params.offset.toString());
    const path = `/jobs${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<JobSpec[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat daftar tugas", []);
  }
};

export const getAgentWorkflowAutomations = async (): Promise<AgentWorkflowAutomationJob[]> => {
  try {
    return await getJson<AgentWorkflowAutomationJob[]>("/automation/agent-workflows");
  } catch (error) {
    return handleApiError(error, "Gagal memuat job otomatis", []);
  }
};

export const upsertAgentWorkflowAutomation = async (
  payload: AgentWorkflowAutomationRequest,
): Promise<AgentWorkflowAutomationJob | undefined> => {
  try {
    return await send<AgentWorkflowAutomationJob>("/automation/agent-workflow", "POST", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menyimpan job otomatis", undefined);
  }
};

export const createJob = async (job: JobSpec): Promise<JobSpec | undefined> => {
  try {
    return await send<JobSpec>("/jobs", "POST", job);
  } catch (error) {
    return handleApiError(error, "Gagal membuat tugas baru", undefined);
  }
};

export const getJobVersions = async (jobId: string, limit = 20): Promise<JobSpecVersion[]> => {
  try {
    const query = new URLSearchParams({ limit: String(limit) });
    return await getJson<JobSpecVersion[]>(`/jobs/${encodeURIComponent(jobId)}/versions?${query.toString()}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat versi job", []);
  }
};

export const rollbackJobVersion = async (
  jobId: string,
  versionId: string,
): Promise<JobRollbackResult | undefined> => {
  try {
    return await send<JobRollbackResult>(
      `/jobs/${encodeURIComponent(jobId)}/rollback/${encodeURIComponent(versionId)}`,
      "POST",
    );
  } catch (error) {
    return handleApiError(error, "Gagal rollback versi job", undefined);
  }
};

export const enableJob = async (jobId: string): Promise<boolean> => {
  try {
    await send<{ job_id: string; status: string }>(`/jobs/${jobId}/enable`, "PUT");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal mengaktifkan tugas", false);
  }
};

export const disableJob = async (jobId: string): Promise<boolean> => {
  try {
    await send<{ job_id: string; status: string }>(`/jobs/${jobId}/disable`, "PUT");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menonaktifkan tugas", false);
  }
};

export const triggerJob = async (jobId: string): Promise<boolean> => {
  try {
    await send<{ run_id: string; status: string }>(`/jobs/${jobId}/run`, "POST");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menjalankan tugas", false);
  }
};

export const getRuns = async (params?: {
  job_id?: string;
  limit?: number;
  status?: RunStatus;
  search?: string;
  offset?: number;
}): Promise<Run[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (params?.job_id) queryParams.append("job_id", params.job_id);
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (params?.status) queryParams.append("status", params.status);
    if (params?.search) queryParams.append("search", params.search);
    if (typeof params?.offset === "number" && params.offset >= 0) queryParams.append("offset", params.offset.toString());
    const path = `/runs${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<Run[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat riwayat eksekusi", []);
  }
};

export const getExperiments = async (params?: {
  enabled?: boolean;
  search?: string;
  limit?: number;
}): Promise<Experiment[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (typeof params?.enabled === "boolean") queryParams.append("enabled", params.enabled ? "true" : "false");
    if (params?.search) queryParams.append("search", params.search);
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    const path = `/experiments${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<Experiment[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat eksperimen", []);
  }
};

export const upsertExperiment = async (
  experimentId: string,
  payload: ExperimentUpsertRequest,
): Promise<Experiment | undefined> => {
  try {
    return await send<Experiment>(`/experiments/${encodeURIComponent(experimentId)}`, "PUT", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menyimpan eksperimen", undefined);
  }
};

export const setExperimentEnabled = async (
  experimentId: string,
  enabled: boolean,
): Promise<Experiment | undefined> => {
  try {
    return await send<Experiment>(`/experiments/${encodeURIComponent(experimentId)}/enabled`, "POST", { enabled });
  } catch (error) {
    return handleApiError(error, "Gagal mengubah status eksperimen", undefined);
  }
};

export const deleteExperiment = async (experimentId: string): Promise<boolean> => {
  try {
    await send<{ experiment_id: string; status: string }>(`/experiments/${encodeURIComponent(experimentId)}`, "DELETE");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menghapus eksperimen", false);
  }
};

export const getRun = async (runId: string): Promise<Run | undefined> => {
  try {
    return await getJson<Run>(`/runs/${runId}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat detail eksekusi", undefined);
  }
};

export const getConnectors = async (): Promise<Connector[]> => {
  try {
    return await getJson<Connector[]>("/connectors");
  } catch (error) {
    return handleApiError(error, "Gagal memuat data koneksi", []);
  }
};

export const getTriggers = async (): Promise<Trigger[]> => {
  try {
    return await getJson<Trigger[]>("/triggers");
  } catch (error) {
    return handleApiError(error, "Gagal memuat trigger", []);
  }
};

export const upsertTrigger = async (
  triggerId: string,
  payload: TriggerUpsertRequest,
): Promise<Trigger | undefined> => {
  try {
    return await send<Trigger>(`/triggers/${encodeURIComponent(triggerId)}`, "PUT", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menyimpan trigger", undefined);
  }
};

export const deleteTrigger = async (triggerId: string): Promise<boolean> => {
  try {
    await send(`/triggers/${encodeURIComponent(triggerId)}`, "DELETE");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menghapus trigger", false);
  }
};

const buildTriggerHeaders = (withJson: boolean, secret?: string): HeadersInit => {
  const headers = buildHeaders(withJson) as Record<string, string>;
  if (secret) {
    headers["X-Trigger-Auth"] = secret;
  }
  return headers;
};

const parseTriggerResponse = async (response: Response): Promise<TriggerFireResponse> => {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Gagal memicu trigger");
  }
  return (await response.json()) as TriggerFireResponse;
};

export const fireTriggerWebhook = async (
  triggerId: string,
  payload: Record<string, unknown>,
  secret?: string,
): Promise<TriggerFireResponse> => {
  const response = await fetch(`${resolveApiBase()}/connectors/webhook/${encodeURIComponent(triggerId)}`, {
    method: "POST",
    headers: buildTriggerHeaders(true, secret),
    body: JSON.stringify(payload),
  });
  return await parseTriggerResponse(response);
};

export const fireTriggerTelegram = async (
  triggerId: string,
  data: { chat_id: string; text: string; username?: string },
  secret?: string,
): Promise<TriggerFireResponse> => {
  const response = await fetch(`${resolveApiBase()}/connectors/telegram/${encodeURIComponent(triggerId)}`, {
    method: "POST",
    headers: buildTriggerHeaders(true, secret),
    body: JSON.stringify(data),
  });
  return await parseTriggerResponse(response);
};

export const fireTriggerEmail = async (
  triggerId: string,
  data: { sender: string; subject: string; body: string },
  secret?: string,
): Promise<TriggerFireResponse> => {
  const response = await fetch(`${resolveApiBase()}/connectors/email/${encodeURIComponent(triggerId)}`, {
    method: "POST",
    headers: buildTriggerHeaders(true, secret),
    body: JSON.stringify(data),
  });
  return await parseTriggerResponse(response);
};

export const fireTriggerSlack = async (
  triggerId: string,
  data: { channel_id: string; user_id: string; command: string; text: string; response_url?: string },
  secret?: string,
): Promise<TriggerFireResponse> => {
  const response = await fetch(`${resolveApiBase()}/connectors/slack/${encodeURIComponent(triggerId)}`, {
    method: "POST",
    headers: buildTriggerHeaders(true, secret),
    body: JSON.stringify(data),
  });
  return await parseTriggerResponse(response);
};

export const fireTriggerSms = async (
  triggerId: string,
  data: { phone_number: string; message: string },
  secret?: string,
): Promise<TriggerFireResponse> => {
  const response = await fetch(`${resolveApiBase()}/connectors/sms/${encodeURIComponent(triggerId)}`, {
    method: "POST",
    headers: buildTriggerHeaders(true, secret),
    body: JSON.stringify(data),
  });
  return await parseTriggerResponse(response);
};

export const fireTriggerVoice = async (
  triggerId: string,
  data: { caller: string; transcript: string; call_id?: string },
  secret?: string,
): Promise<TriggerFireResponse> => {
  const response = await fetch(`${resolveApiBase()}/connectors/voice/${encodeURIComponent(triggerId)}`, {
    method: "POST",
    headers: buildTriggerHeaders(true, secret),
    body: JSON.stringify(data),
  });
  return await parseTriggerResponse(response);
};

export const getSkills = async (tags?: string[]): Promise<Skill[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (tags?.length) {
      queryParams.append("tags", tags.join(","));
    }
    const path = `/skills${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<Skill[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat skill", []);
  }
};

export const upsertSkill = async (skillId: string, payload: SkillSpecRequest): Promise<Skill | undefined> => {
  try {
    return await send<Skill>(`/skills/${encodeURIComponent(skillId)}`, "PUT", payload);
  } catch (error) {
    return handleApiError(error, `Gagal menyimpan skill ${skillId}`, undefined);
  }
};

export const deleteSkill = async (skillId: string): Promise<boolean> => {
  try {
    await send(`/skills/${encodeURIComponent(skillId)}`, "DELETE");
    return true;
  } catch (error) {
    return handleApiError(error, `Gagal menghapus skill ${skillId}`, false);
  }
};

export const syncSkills = async (skills: SkillSpecRequest[]): Promise<Skill[] | undefined> => {
  try {
    return await send<Skill[]>("/skills/sync", "POST", { skills });
  } catch (error) {
    return handleApiError(error, "Gagal sinkron skill", undefined);
  }
};

export const getTelegramConnectorAccounts = async (): Promise<TelegramConnectorAccount[]> => {
  try {
    return await getJson<TelegramConnectorAccount[]>("/connector/telegram/accounts");
  } catch (error) {
    return handleApiError(error, "Gagal memuat akun Telegram", []);
  }
};

export const upsertTelegramConnectorAccount = async (
  accountId: string,
  payload: TelegramConnectorAccountUpsertRequest,
): Promise<TelegramConnectorAccount | undefined> => {
  try {
    return await send<TelegramConnectorAccount>(`/connector/telegram/accounts/${accountId}`, "PUT", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menyimpan akun Telegram", undefined);
  }
};

export const deleteTelegramConnectorAccount = async (accountId: string): Promise<boolean> => {
  try {
    await send<{ account_id: string; status: string }>(`/connector/telegram/accounts/${accountId}`, "DELETE");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menghapus akun Telegram", false);
  }
};

export const getMcpIntegrationServers = async (): Promise<McpIntegrationServer[]> => {
  try {
    return await getJson<McpIntegrationServer[]>("/integrations/mcp/servers");
  } catch (error) {
    return handleApiError(error, "Gagal memuat daftar MCP server", []);
  }
};

export const upsertMcpIntegrationServer = async (
  serverId: string,
  payload: McpIntegrationServerUpsertRequest,
): Promise<McpIntegrationServer | undefined> => {
  try {
    return await send<McpIntegrationServer>(`/integrations/mcp/servers/${serverId}`, "PUT", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menyimpan MCP server", undefined);
  }
};

export const deleteMcpIntegrationServer = async (serverId: string): Promise<boolean> => {
  try {
    await send<{ server_id: string; status: string }>(`/integrations/mcp/servers/${serverId}`, "DELETE");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menghapus MCP server", false);
  }
};

export const getIntegrationAccounts = async (provider?: string): Promise<IntegrationAccount[]> => {
  try {
    const query = provider ? `?provider=${encodeURIComponent(provider)}` : "";
    return await getJson<IntegrationAccount[]>(`/integrations/accounts${query}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat akun integrasi", []);
  }
};

export const upsertIntegrationAccount = async (
  provider: string,
  accountId: string,
  payload: IntegrationAccountUpsertRequest,
): Promise<IntegrationAccount | undefined> => {
  try {
    return await send<IntegrationAccount>(`/integrations/accounts/${provider}/${accountId}`, "PUT", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menyimpan akun integrasi", undefined);
  }
};

export const deleteIntegrationAccount = async (provider: string, accountId: string): Promise<boolean> => {
  try {
    await send<{ provider: string; account_id: string; status: string }>(
      `/integrations/accounts/${provider}/${accountId}`,
      "DELETE",
    );
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menghapus akun integrasi", false);
  }
};

export const getIntegrationsCatalog = async (): Promise<IntegrationsCatalog> => {
  try {
    return await getJson<IntegrationsCatalog>("/integrations/catalog");
  } catch (error) {
    return handleApiError(error, "Gagal memuat katalog konektor", { providers: [], mcp_servers: [] });
  }
};

export const bootstrapIntegrationsCatalog = async (
  payload: IntegrationsBootstrapRequest,
): Promise<IntegrationsBootstrapResponse | undefined> => {
  try {
    return await send<IntegrationsBootstrapResponse>("/integrations/catalog/bootstrap", "POST", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menambahkan template konektor", undefined);
  }
};

export const getAgents = async (): Promise<Agent[]> => {
  try {
    return await getJson<Agent[]>("/agents");
  } catch (error) {
    return handleApiError(error, "Gagal memuat data agen", []);
  }
};

export const getAgentMemories = async (limit = 100): Promise<AgentMemorySummary[]> => {
  try {
    const query = new URLSearchParams({ limit: String(limit) });
    return await getJson<AgentMemorySummary[]>(`/agents/memory?${query.toString()}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat memori agen", []);
  }
};

export const resetAgentMemory = async (agentKey: string): Promise<AgentMemoryResetResponse | undefined> => {
  try {
    return await send<AgentMemoryResetResponse>(`/agents/memory/${encodeURIComponent(agentKey)}`, "DELETE");
  } catch (error) {
    return handleApiError(error, "Gagal reset memori agen", undefined);
  }
};

export const checkHealth = async () => {
  try {
    const [healthResponse, readyResponse] = await Promise.all([
      fetch(`${resolveApiBase()}/healthz`),
      fetch(`${resolveApiBase()}/readyz`),
    ]);

    return {
      apiHealthy: healthResponse.ok,
      systemReady: readyResponse.ok,
    };
  } catch {
    return {
      apiHealthy: false,
      systemReady: false,
    };
  }
};

export const getQueueMetrics = async (): Promise<{ depth: number; delayed: number }> => {
  try {
    return await getJson<{ depth: number; delayed: number }>("/queue");
  } catch (error) {
    return handleApiError(error, "Gagal memuat metrik antrean", { depth: 0, delayed: 0 });
  }
};

export const getSystemMetrics = async (): Promise<SystemMetrics> => {
  const [health, queue, agents] = await Promise.all([checkHealth(), getQueueMetrics(), getAgents()]);
  return {
    queue_depth: queue.depth,
    delayed_count: queue.delayed,
    worker_count: agents.filter((agent) => agent.type !== "scheduler").length,
    scheduler_online: agents.some((agent) => agent.type === "scheduler" && agent.status === "online"),
    redis_online: health.systemReady,
    api_online: health.apiHealthy,
  };
};

export const getEvents = async (params?: {
  since?: string;
  limit?: number;
  offset?: number;
  event_type?: string;
  search?: string;
}): Promise<SystemEvent[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (params?.since) queryParams.append("since", params.since);
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (typeof params?.offset === "number" && params.offset >= 0) queryParams.append("offset", params.offset.toString());
    if (params?.event_type) queryParams.append("event_type", params.event_type);
    if (params?.search) queryParams.append("search", params.search);
    const path = `/events${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<SystemEvent[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat update skill", []);
  }
};

export const getAuditLogs = async (params?: {
  since?: string;
  limit?: number;
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  outcome?: "success" | "error" | "denied";
  actor_role?: "viewer" | "operator" | "admin" | "unknown";
  path_constains?: string;
}): Promise<AuditLog[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (params?.since) queryParams.append("since", params.since);
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    if (params?.method) queryParams.append("method", params.method);
    if (params?.outcome) queryParams.append("outcome", params.outcome);
    if (params?.actor_role) queryParams.append("actor_role", params.actor_role);
    if (params?.path_constains) queryParams.append("path_constains", params.path_constains);
    const path = `/audit/logs${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<AuditLog[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat audit log", []);
  }
};

export const getApprovalRequests = async (params?: {
  status?: ApprovalStatus;
  limit?: number;
}): Promise<ApprovalRequest[]> => {
  try {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.append("status", params.status);
    if (params?.limit) queryParams.append("limit", params.limit.toString());
    const path = `/approvals${queryParams.size ? `?${queryParams.toString()}` : ""}`;
    return await getJson<ApprovalRequest[]>(path);
  } catch (error) {
    return handleApiError(error, "Gagal memuat approval queue", []);
  }
};

export const approveApprovalRequest = async (
  approvalId: string,
  payload?: { decision_by?: string; decision_note?: string },
): Promise<ApprovalRequest | undefined> => {
  try {
    return await send<ApprovalRequest>(`/approvals/${approvalId}/approve`, "POST", payload || {});
  } catch (error) {
    return handleApiError(error, "Gagal approve request", undefined);
  }
};

export const rejectApprovalRequest = async (
  approvalId: string,
  payload?: { decision_by?: string; decision_note?: string },
): Promise<ApprovalRequest | undefined> => {
  try {
    return await send<ApprovalRequest>(`/approvals/${approvalId}/reject`, "POST", payload || {});
  } catch (error) {
    return handleApiError(error, "Gagal menolak request", undefined);
  }
};

export interface Squad {
  hunter_job_id?: string;
  marketer_job_id?: string;
  closer_job_id?: string;
}

export interface InfluencerTemplate {
  template_id: string;
  name: string;
  mode: "endorse" | "product" | "hybrid" | string;
  description: string;
  enabled: boolean;
  default_branch_id: string;
  branch_blueprint_id: string;
  channels_required: string[];
  job_templates: Record<string, unknown>[];
  metadata: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface InfluencerProfile {
  influencer_id: string;
  name: string;
  niche: string;
  mode: "endorse" | "product" | "hybrid" | string;
  status: string;
  template_id: string;
  branch_id: string;
  channels: Record<string, string>;
  offer_name: string;
  offer_price: number;
  metadata: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface CloneInfluencerTemplateRequest {
  influencer_id?: string;
  name: string;
  niche?: string;
  mode?: "endorse" | "product" | "hybrid" | string;
  branch_id?: string;
  channels?: Record<string, string>;
  offer_name?: string;
  offer_price?: number;
  metadata?: Record<string, unknown>;
  enable_jobs?: boolean;
  overwrite_existing_jobs?: boolean;
}

export interface CloneInfluencerJobResult {
  job_id: string;
  type: string;
  enabled: boolean;
  status: "created" | "updated" | "skipped_existing" | string;
}

export interface CloneInfluencerTemplateResponse {
  template_id: string;
  influencer: InfluencerProfile;
  jobs: CloneInfluencerJobResult[];
  status: "ok" | string;
}

export interface UpdateInfluencerProfileRequest {
  name?: string;
  niche?: string;
  mode?: "endorse" | "product" | "hybrid" | string;
  status?: string;
  template_id?: string;
  branch_id?: string;
  channels?: Record<string, string>;
  offer_name?: string;
  offer_price?: number;
  metadata?: Record<string, unknown>;
  apply_template_jobs?: boolean;
  enable_jobs?: boolean;
  overwrite_existing_jobs?: boolean;
}

export interface UpdateInfluencerProfileResponse {
  influencer: InfluencerProfile;
  jobs: CloneInfluencerJobResult[];
  status: "ok" | string;
}

export interface Branch {
  branch_id: string;
  name: string;
  status: "active" | "paused" | "closed";
  blueprint_id: string;
  target_kpi: Record<string, any>;
  current_metrics: {
    revenue: number;
    leads: number;
    closings: number;
  };
  operational_ready?: Record<string, number>;
  squad: Squad;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

export interface SalesInboundRequest {
  branch_id: string;
  channel: string;
  contact_id: string;
  name?: string;
  source?: string;
  offer?: string;
  owner?: string;
  message?: string;
  value_estimate?: number;
  tags?: string[];
  stage?: string;
  auto_followup?: boolean;
  account_id?: string;
  followup_template?: string;
  next_followup_minutes?: number;
}

export interface SalesInboundResponse {
  status: string;
  action: "created" | "updated" | string;
  prospect_id: string;
  branch_id: string;
  channel: string;
  contact_id: string;
  followup_queued: boolean;
  run_id?: string;
}

export const getBranches = async (): Promise<Branch[]> => {
  try {
    return await getJson<Branch[]>("/branches");
  } catch (error) {
    return handleApiError(error, "Gagal memuat unit bisnis", []);
  }
};

export const submitSalesInbound = async (
  payload: SalesInboundRequest,
): Promise<SalesInboundResponse | undefined> => {
  try {
    return await send<SalesInboundResponse>("/sales/inbound", "POST", payload);
  } catch (error) {
    return handleApiError(error, "Gagal memproses inbound sales", undefined);
  }
};

export const getInfluencerTemplates = async (limit = 200): Promise<InfluencerTemplate[]> => {
  try {
    const query = new URLSearchParams({ limit: String(limit) });
    return await getJson<InfluencerTemplate[]>(`/influencer/templates?${query.toString()}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat template influencer", []);
  }
};

export interface ListInfluencerProfilesParams {
  limit?: number;
}

export const getInfluencerProfiles = async (
  params?: ListInfluencerProfilesParams,
): Promise<InfluencerProfile[]> => {
  try {
    const query = new URLSearchParams({ limit: String(params?.limit ?? 200) });
    return await getJson<InfluencerProfile[]>(`/influencer/profiles?${query.toString()}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat profile influencer", []);
  }
};

export const getInfluencerProfile = async (influencerId: string): Promise<InfluencerProfile | undefined> => {
  try {
    return await getJson<InfluencerProfile>(`/influencer/profiles/${encodeURIComponent(influencerId)}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat profile influencer", undefined);
  }
};

export const cloneInfluencerFromTemplate = async (
  templateId: string,
  payload: CloneInfluencerTemplateRequest,
): Promise<CloneInfluencerTemplateResponse | undefined> => {
  try {
    return await send<CloneInfluencerTemplateResponse>(
      `/influencer/templates/${encodeURIComponent(templateId)}/clone`,
      "POST",
      payload,
    );
  } catch (error) {
    return handleApiError(error, "Gagal clone template influencer", undefined);
  }
};

export const updateInfluencerProfile = async (
  influencerId: string,
  payload: UpdateInfluencerProfileRequest,
): Promise<UpdateInfluencerProfileResponse | undefined> => {
  try {
    return await send<UpdateInfluencerProfileResponse>(
      `/influencer/profiles/${encodeURIComponent(influencerId)}`,
      "PATCH",
      payload,
    );
  } catch (error) {
    return handleApiError(error, "Gagal update profile influencer", undefined);
  }
};

export interface Account {
  account_id: string;
  platform: string;
  username: string;
  proxy?: string;
  two_factor_key?: string;
  status: "pending" | "verifying" | "ready" | "cooldown" | "action_required" | "banned";
  branch_id?: string;
  created_at: string;
  updated_at: string;
  metadata: Record<string, any>;
}

export const getArmoryAccounts = async (platform?: string): Promise<Account[]> => {
  try {
    const query = platform ? `?platform=${platform}` : "";
    return await getJson<Account[]>(`/armory/accounts${query}`);
  } catch (error) {
    return handleApiError(error, "Gagal memuat daftar akun", []);
  }
};

export const addArmoryAccount = async (payload: any): Promise<Account | undefined> => {
  try {
    return await send<Account>("/armory/accounts", "POST", payload);
  } catch (error) {
    return handleApiError(error, "Gagal menambahkan akun", undefined);
  }
};

export const deployAccount = async (accountId: string, branchId: string): Promise<boolean> => {
  try {
    await send(`/armory/accounts/${accountId}/deploy?branch_id=${branchId}`, "POST");
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal menugaskan akun", false);
  }
};

export interface ChatMessage {
  id: string;
  sender: "Chairman" | "CEO" | string;
  text: string;
  timestamp: string;
}

export const getBoardroomHistory = async (): Promise<ChatMessage[]> => {
  try {
    return await getJson<ChatMessage[]>("/boardroom/history");
  } catch (error) {
    return handleApiError(error, "Gagal memuat riwayat chat", []);
  }
};

export const sendChairmanMandate = async (text: string): Promise<boolean> => {
  try {
    await send("/boardroom/chat", "POST", { text });
    return true;
  } catch (error) {
    return handleApiError(error, "Gagal mengirim mandat", false);
  }
};

export const getSystemInfrastructure = async (): Promise<any> => {
  try {
    return await getJson("/system/infrastructure");
  } catch (error) {
    return { api: { status: "error" }, redis: { status: "error" }, ai_factory: { status: "error" } };
  }
};

export const executePlannerPrompt = async (payload: PlannerExecuteRequest): Promise<PlannerExecuteResponse> => {
  return await send<PlannerExecuteResponse>("/planner/execute", "POST", payload);
};
export interface MemoryEntry {
  key: string;
  value: unknown;
}

export const getMemory = async (): Promise<MemoryEntry[]> => getJson<MemoryEntry[]>("/memory");
export const saveMemory = async (data: any): Promise<unknown> => send<unknown>("/memory", "POST", data);
