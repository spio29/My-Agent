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
  getSystemMetrics,
  getTelegramConnectorAccounts,
  setApiAuthToken,
} from "@/lib/api";

const summarizeEvent = (type: string): string => {
  const normalized = type.toLowerCase();

  if (normalized.includes("telegram")) return "Notification lane updated";
  if (normalized.includes("auth") || normalized.includes("token")) return "Access updated";
  if (normalized.includes("approval")) return "Approval flow updated";
  if (normalized.includes("settings") || normalized.includes("config")) return "Workspace setting updated";

  return type
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

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
  const eventsQuery = useQuery({
    queryKey: ["settings", "events"],
    queryFn: () => getEvents({ limit: 8 }),
  });

  const refreshAll = async () => {
    await Promise.all([
      metricsQuery.refetch(),
      telegramQuery.refetch(),
      eventsQuery.refetch(),
    ]);
  };

  const enabledTelegramAccounts = useMemo(
    () => (telegramQuery.data || []).filter((item) => item.enabled),
    [telegramQuery.data],
  );
  const readyTelegramAccounts = useMemo(
    () => enabledTelegramAccounts.filter((item) => item.has_bot_token),
    [enabledTelegramAccounts],
  );
  const activeChatTargets = useMemo(() => {
    const uniqueTargets = new Set<string>();

    for (const account of enabledTelegramAccounts) {
      for (const chatId of account.allowed_chat_ids || []) {
        if (chatId) uniqueTargets.add(chatId);
      }
    }

    return uniqueTargets;
  }, [enabledTelegramAccounts]);
  const defaultChannels = useMemo(() => {
    const uniqueChannels = new Set<string>();

    for (const account of enabledTelegramAccounts) {
      if (account.default_channel) uniqueChannels.add(account.default_channel);
    }

    return uniqueChannels;
  }, [enabledTelegramAccounts]);
  const configurationEvents = useMemo(
    () =>
      (eventsQuery.data || []).filter((event) =>
        /telegram|auth|token|settings|config|approval/.test(event.type),
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
          Configuration workspace for operator access, runtime health, and
          delivery lanes.
        </p>
      </div>

      <SectionShell
        title="Configuration"
        description="Store the operator API token locally and confirm the workspace is using the expected upstream."
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
                metricsQuery.isFetching || telegramQuery.isFetching || eventsQuery.isFetching
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
              <p className="text-sm text-slate-500">Workspace target</p>
              <p className="mt-1 text-sm font-medium text-slate-900">
                amazing.spio.digital routed through the operator workspace on `/api`.
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
          title="Delivery lanes"
          description="Counts for operator-facing notification lanes and their current routing targets."
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Ready lanes</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {readyTelegramAccounts.length}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Enabled lanes</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {enabledTelegramAccounts.length}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
              <p className="text-sm text-slate-500">Chat targets</p>
              <p className="mt-1 text-2xl font-semibold tracking-[-0.03em] text-slate-950">
                {activeChatTargets.size}
              </p>
            </article>
          </div>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <article className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <p className="text-sm text-slate-500">Ready accounts</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {readyTelegramAccounts.length > 0
                  ? readyTelegramAccounts
                      .slice(0, 5)
                      .map((item) => item.account_id)
                      .join(", ")
                  : "Belum ada lane siap pakai."}
              </p>
            </article>
            <article className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <p className="text-sm text-slate-500">Default channels</p>
              <p className="mt-2 text-sm leading-6 text-slate-700">
                {defaultChannels.size > 0
                  ? Array.from(defaultChannels).slice(0, 5).join(", ")
                  : "Belum ada channel default yang dikonfigurasi."}
              </p>
            </article>
          </div>
        </SectionShell>
      </div>

      <SectionShell
        title="Recent setup signals"
        description="Recent access and notification events that help explain the current workspace state."
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
