"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { toast } from "sonner";

import SectionShell from "@/components/operator/section-shell";
import StatusPill from "@/components/operator/status-pill";
import {
  clearApiAuthToken,
  getApiAuthToken,
  getEvents,
  getIntegrationAccounts,
  getIntegrationsCatalog,
  getMcpIntegrationServers,
  getSystemMetrics,
  getTelegramConnectorAccounts,
  setApiAuthToken,
} from "@/lib/api";

const summarizeEvent = (type: string): string =>
  type
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

export default function SettingsPage() {
  const [tokenDraft, setTokenDraft] = useState("");
  const [savedToken, setSavedToken] = useState(false);

  useEffect(() => {
    const currentToken = getApiAuthToken();
    setTokenDraft(currentToken);
    setSavedToken(Boolean(currentToken));
  }, []);

  const metricsQuery = useQuery({
    queryKey: ["settings", "metrics"],
    queryFn: () => getSystemMetrics(),
  });
  const telegramQuery = useQuery({
    queryKey: ["settings", "telegram"],
    queryFn: () => getTelegramConnectorAccounts(),
  });
  const integrationsQuery = useQuery({
    queryKey: ["settings", "integrations"],
    queryFn: () => getIntegrationAccounts(),
  });
  const mcpQuery = useQuery({
    queryKey: ["settings", "mcp"],
    queryFn: () => getMcpIntegrationServers(),
  });
  const catalogQuery = useQuery({
    queryKey: ["settings", "catalog"],
    queryFn: () => getIntegrationsCatalog(),
  });
  const eventsQuery = useQuery({
    queryKey: ["settings", "events"],
    queryFn: () => getEvents({ limit: 8 }),
  });

  const refreshAll = async () => {
    await Promise.all([
      metricsQuery.refetch(),
      telegramQuery.refetch(),
      integrationsQuery.refetch(),
      mcpQuery.refetch(),
      catalogQuery.refetch(),
      eventsQuery.refetch(),
    ]);
  };

  const enabledIntegrations = useMemo(
    () => (integrationsQuery.data || []).filter((item) => item.enabled),
    [integrationsQuery.data],
  );
  const enabledMcpServers = useMemo(
    () => (mcpQuery.data || []).filter((item) => item.enabled),
    [mcpQuery.data],
  );
  const readyTelegramAccounts = useMemo(
    () =>
      (telegramQuery.data || []).filter((item) => item.enabled && item.has_bot_token),
    [telegramQuery.data],
  );
  const configurationEvents = useMemo(
    () =>
      (eventsQuery.data || []).filter((event) =>
        /integration|connector|approval|automation/.test(event.type),
      ),
    [eventsQuery.data],
  );

  const saveToken = () => {
    setApiAuthToken(tokenDraft);
    setSavedToken(Boolean(tokenDraft.trim()));
    toast.success(tokenDraft.trim() ? "Token API tersimpan." : "Token API dikosongkan.");
  };

  const clearToken = () => {
    clearApiAuthToken();
    setTokenDraft("");
    setSavedToken(false);
    toast.success("Token API dihapus dari browser.");
  };

  const metrics = metricsQuery.data || {
    queue_depth: 0,
    delayed_count: 0,
    worker_count: 0,
    scheduler_online: false,
    redis_online: false,
    api_online: false,
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
      <div className="max-w-3xl">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Settings</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Configuration workspace for operator access, system readiness, and
          integration inventory without reopening the previous setup surface.
        </p>
      </div>

      <SectionShell
        title="Configuration"
        description="Store the operator API token locally and confirm the preview app is pointing at the expected upstream."
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
                metricsQuery.isFetching ||
                telegramQuery.isFetching ||
                integrationsQuery.isFetching ||
                mcpQuery.isFetching ||
                catalogQuery.isFetching ||
                eventsQuery.isFetching
                  ? "animate-spin"
                  : ""
              }`}
            />
            Refresh
          </button>
        }
      >
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="space-y-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate-700">
                Token API
              </span>
              <input
                value={tokenDraft}
                onChange={(event) => setTokenDraft(event.target.value)}
                placeholder="Paste viewer/operator/admin token"
                className="h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400"
              />
            </label>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={saveToken}
                className="rounded-md border border-slate-900 bg-slate-900 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-800"
              >
                Save token
              </button>
              <button
                type="button"
                onClick={clearToken}
                className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
              >
                Clear token
              </button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Stored access</p>
              <div className="mt-2">
                <StatusPill tone={savedToken ? "success" : "warning"}>
                  {savedToken ? "Token available" : "Token missing"}
                </StatusPill>
              </div>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">API base</p>
              <p className="mt-1 text-sm font-medium text-slate-900">
                {process.env.NEXT_PUBLIC_API_BASE || "/api"}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3 sm:col-span-2">
              <p className="text-sm text-slate-500">Template catalog</p>
              <p className="mt-1 text-sm font-medium text-slate-900">
                {catalogQuery.data?.providers.length || 0} provider template ·{" "}
                {catalogQuery.data?.mcp_servers.length || 0} MCP template
              </p>
            </article>
          </div>
        </div>
      </SectionShell>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <SectionShell
          title="System readiness"
          description="Health snapshot for queue, workers, and scheduler before the operator starts a new action."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">API</p>
              <div className="mt-2">
                <StatusPill tone={metrics.api_online ? "success" : "critical"}>
                  {metrics.api_online ? "Online" : "Offline"}
                </StatusPill>
              </div>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Scheduler</p>
              <div className="mt-2">
                <StatusPill tone={metrics.scheduler_online ? "success" : "warning"}>
                  {metrics.scheduler_online ? "Online" : "Needs attention"}
                </StatusPill>
              </div>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Queue depth</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {metrics.queue_depth}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Delayed jobs</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {metrics.delayed_count}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3 sm:col-span-2">
              <p className="text-sm text-slate-500">Worker pool</p>
              <p className="mt-1 text-sm font-medium text-slate-900">
                {metrics.worker_count} worker · Redis{" "}
                {metrics.redis_online ? "ready" : "not ready"}
              </p>
            </article>
          </div>
        </SectionShell>

        <SectionShell
          title="Integration inventory"
          description="Current counts for operator-facing connectors, providers, and MCP servers."
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Provider accounts</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {enabledIntegrations.length}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">MCP servers</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {enabledMcpServers.length}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Telegram lanes</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {readyTelegramAccounts.length}
              </p>
            </article>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-3">
            <article className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <p className="text-sm text-slate-500">Providers</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {enabledIntegrations.length > 0
                  ? enabledIntegrations
                      .slice(0, 5)
                      .map((item) => `${item.provider}/${item.account_id}`)
                      .join(", ")
                  : "Belum ada akun provider aktif."}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <p className="text-sm text-slate-500">MCP servers</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {enabledMcpServers.length > 0
                  ? enabledMcpServers
                      .slice(0, 5)
                      .map((item) => item.server_id)
                      .join(", ")
                  : "Belum ada MCP server aktif."}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <p className="text-sm text-slate-500">Telegram</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {readyTelegramAccounts.length > 0
                  ? readyTelegramAccounts
                      .slice(0, 5)
                      .map((item) => item.account_id)
                      .join(", ")
                  : "Belum ada akun Telegram siap pakai."}
              </p>
            </article>
          </div>
        </SectionShell>
      </div>

      <SectionShell
        title="Recent setup signals"
        description="Recent configuration-oriented events that help explain the current workspace state."
      >
        <div className="divide-y divide-slate-200">
          {configurationEvents.length === 0 ? (
            <div className="py-4 text-sm text-slate-500">
              Belum ada event konfigurasi terbaru yang bisa ditampilkan.
            </div>
          ) : (
            configurationEvents.map((event) => (
              <article key={event.id} className="py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4 className="text-sm font-semibold text-slate-950">
                    {summarizeEvent(event.type)}
                  </h4>
                  <span className="text-sm text-slate-500">
                    {formatTimestamp(event.timestamp)}
                  </span>
                </div>
                <p className="mt-1 text-sm leading-6 text-slate-600">
                  {Object.keys(event.data || {}).length > 0
                    ? Object.entries(event.data || {})
                        .slice(0, 4)
                        .map(([key, value]) => `${key}: ${String(value)}`)
                        .join(" · ")
                    : "Tidak ada detail tambahan."}
                </p>
              </article>
            ))
          )}
        </div>
      </SectionShell>
    </div>
  );
}
