"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bot,
  Briefcase,
  Building2,
  CheckCircle2,
  MessageSquareQuote,
  Send,
  ShieldCheck,
  Target,
  TrendingUp,
  User,
  Zap,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getBranches,
  getBoardroomHistory,
  getSystemInfrastructure,
  sendChairmanMandate,
  type Branch,
} from "@/lib/api";

const formatCurrency = (val: number) =>
  new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(val || 0);

const sanitizeBoardroomText = (text: string) =>
  text
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/<\/?\s*think\s*>/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

const getBranchReadiness = (branch: Branch): number => {
  const values = Object.values(branch.operational_ready || {}).filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  if (values.length === 0) return 0;
  const normalized = values.map((value) => (value <= 1 ? value * 100 : value));
  const average = normalized.reduce((sum, value) => sum + value, 0) / normalized.length;
  return Math.max(0, Math.min(100, Math.round(average)));
};

const getStatusStyle = (status: Branch["status"]) => {
  if (status === "active") return "border-sky-200/80 bg-sky-100 text-sky-700";
  if (status === "paused") return "border-white bg-white/80 text-blue-900/60";
  return "border-white bg-white/80 text-blue-900/60";
};

const parseInfraStatus = (status?: string) => {
  const value = String(status || "").toLowerCase();
  if (value === "ok" || value === "ready") return "online";
  if (!value) return "checking";
  return "attention";
};

export default function ChairmanDashboard() {
  const queryClient = useQueryClient();
  const [activeBranchId, setActiveBranchId] = useState<string | null>(null);
  const [mandateText, setMandateText] = useState("");

  const { data: branches = [] } = useQuery({
    queryKey: ["branches"],
    queryFn: getBranches,
    refetchInterval: 5000,
  });

  const { data: infra = {} } = useQuery({
    queryKey: ["system-infra"],
    queryFn: getSystemInfrastructure,
    refetchInterval: 3000,
  });

  const { data: chatHistory = [] } = useQuery({
    queryKey: ["boardroom-chat"],
    queryFn: getBoardroomHistory,
    refetchInterval: 3000,
  });

  const mandateMutation = useMutation({
    mutationFn: sendChairmanMandate,
    onSuccess: () => {
      setMandateText("");
      queryClient.invalidateQueries({ queryKey: ["boardroom-chat"] });
    },
  });

  const sanitizedChatHistory = useMemo(
    () =>
      chatHistory
        .map((msg) => {
          const cleanedText = msg.sender === "CEO" ? sanitizeBoardroomText(msg.text) : msg.text.trim();
          return { ...msg, text: cleanedText };
        })
        .filter((msg) => msg.text.length > 0),
    [chatHistory],
  );

  const totalRevenue = useMemo(
    () => branches.reduce((sum, branch) => sum + (branch.current_metrics?.revenue || 0), 0),
    [branches],
  );
  const totalLeads = useMemo(
    () => branches.reduce((sum, branch) => sum + (branch.current_metrics?.leads || 0), 0),
    [branches],
  );
  const activeUnits = useMemo(() => branches.filter((branch) => branch.status === "active").length, [branches]);
  const readinessAverage = useMemo(() => {
    if (branches.length === 0) return 0;
    return Math.round(branches.reduce((sum, branch) => sum + getBranchReadiness(branch), 0) / branches.length);
  }, [branches]);

  const activeBranch = useMemo(
    () => branches.find((branch) => branch.branch_id === activeBranchId) || null,
    [branches, activeBranchId],
  );

  const latestCeoMessage = useMemo(() => {
    const ceoMessages = [...sanitizedChatHistory].reverse().filter((message) => message.sender === "CEO");
    return ceoMessages[0]?.text || "CEO belum mengirim ringkasan terbaru.";
  }, [sanitizedChatHistory]);

  useEffect(() => {
    if (branches.length === 0) {
      if (activeBranchId !== null) setActiveBranchId(null);
      return;
    }
    const stillExists = branches.some((branch) => branch.branch_id === activeBranchId);
    if (!stillExists) {
      setActiveBranchId(branches[0].branch_id);
    }
  }, [branches, activeBranchId]);

  const handleSendMandate = (event: React.FormEvent) => {
    event.preventDefault();
    if (!mandateText.trim()) return;
    mandateMutation.mutate(mandateText);
  };

  const healthItems = [
    { label: "API", value: infra.api?.status?.toUpperCase() || "CHECKING", state: parseInfraStatus(infra.api?.status) },
    { label: "REDIS", value: infra.redis?.memory_used || "OFFLINE", state: parseInfraStatus(infra.redis?.status) },
    {
      label: "AI FACTORY",
      value: infra.ai_factory?.status?.toUpperCase() || "NOT CONFIGURED",
      state: parseInfraStatus(infra.ai_factory?.status),
    },
  ];

  const pipelineMaturity = activeBranch
    ? Math.min(
        100,
        (activeBranch.current_metrics?.closings || 0) > 0 ? 100 : (activeBranch.current_metrics?.leads || 0) > 0 ? 60 : 25,
      )
    : 0;

  return (
    <div className="ux-rise-in mx-auto flex h-full min-h-0 max-w-[1600px] flex-col gap-3 text-slate-900">
      <section className="glass-island shrink-0 p-4 md:p-5">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-2">
            <p className="inline-flex items-center gap-2 rounded-2xl border border-sky-200/80 bg-sky-100 px-3 py-1 text-xs font-bold tracking-tight text-sky-700">
              <ShieldCheck className="h-3.5 w-3.5" />
              Live Executive Dashboard
            </p>
            <div className="flex items-start gap-3">
              <div className="glass-island rounded-2xl p-3 text-slate-900">
                <Building2 className="h-6 w-6" />
              </div>
              <div>
                <h1 className="text-2xl font-black tracking-tighter text-slate-900 md:text-3xl">Sovereign Cockpit</h1>
                <p className="text-xs text-blue-900/60 md:text-sm">
                  Command center untuk memonitor pertumbuhan, operasi, dan eksekusi mandatori cabang.
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 xl:w-[560px]">
            {healthItems.map((item) => (
              <div
                key={item.label}
                className={`rounded-2xl border px-3 py-2 shadow-xl shadow-blue-900/5 backdrop-blur-xl ${
                  item.state === "online"
                    ? "border-sky-200/80 bg-sky-100 text-sky-700"
                    : "border-white bg-white/70 text-blue-900/60"
                }`}
              >
                <p className="text-[10px] font-bold uppercase tracking-[0.16em]">
                  {item.label}
                </p>
                <p className={`mt-1 text-sm font-black tracking-tight ${item.state === "online" ? "text-sky-700" : "text-slate-900"}`}>
                  {item.value}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <Card className="metric-card-hover">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-900/60">Total Revenue</p>
              <p className="metric-number text-3xl">{formatCurrency(totalRevenue)}</p>
              <p className="mt-1 text-[11px] text-blue-900/60">Across all active branches</p>
            </CardContent>
          </Card>

          <Card className="metric-card-hover">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-900/60">Active Units</p>
              <p className="metric-number text-3xl">{activeUnits}</p>
              <p className="mt-1 text-[11px] text-blue-900/60">{branches.length} units terdaftar</p>
            </CardContent>
          </Card>

          <Card className="metric-card-hover">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-900/60">Pipeline Leads</p>
              <p className="metric-number text-3xl">{totalLeads}</p>
              <p className="mt-1 text-[11px] text-blue-900/60">Total leads yang masuk ke funnel</p>
            </CardContent>
          </Card>

          <Card className="metric-card-hover">
            <CardContent className="p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-blue-900/60">Operational Readiness</p>
              <p className="metric-number text-3xl">{readinessAverage}%</p>
              <div className="mt-2 h-2 w-full rounded-full bg-white/70">
                <div className="h-full rounded-full bg-slate-900 transition-all" style={{ width: `${readinessAverage}%` }} />
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      <section className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[1.18fr_0.82fr]">
        <div className="flex min-h-0 flex-col gap-3">
          <Card className="min-h-0 flex flex-col">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg font-black tracking-tighter text-slate-900">Strategic Business Units</CardTitle>
              <p className="text-[11px] text-blue-900/60">
                Pantau performa unit dan prioritas eksekusi cepat.
              </p>
            </CardHeader>
            <CardContent className="no-scrollbar flex-1 overflow-y-auto p-4 pt-0">
              <div className="grid h-full auto-rows-fr gap-2 md:grid-cols-2 xl:grid-cols-3">
                {branches.map((branch) => {
                  const readiness = getBranchReadiness(branch);
                  const isActive = branch.branch_id === activeBranchId;
                  return (
                    <button
                      key={branch.branch_id}
                      onClick={() => setActiveBranchId(branch.branch_id)}
                      className={`rounded-2xl border p-3 text-left transition-all ${
                        isActive
                          ? "border-sky-200/80 bg-sky-100 shadow-lg shadow-blue-900/10"
                          : "border-white bg-white/75 hover:-translate-y-0.5"
                      }`}
                    >
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <div>
                          <p className="text-sm font-black tracking-tight text-slate-900">{branch.name}</p>
                          <p className="text-[10px] text-blue-900/60">{branch.branch_id}</p>
                        </div>
                        <span className={`rounded-xl border px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.1em] ${getStatusStyle(branch.status)}`}>
                          {branch.status}
                        </span>
                      </div>
                      <div className="grid grid-cols-3 gap-1.5 text-center">
                        <div className="rounded-xl bg-white/70 p-2">
                          <p className="text-[10px] text-blue-900/60">Leads</p>
                          <p className="metric-number text-lg">{branch.current_metrics?.leads || 0}</p>
                        </div>
                        <div className="rounded-xl bg-white/70 p-2">
                          <p className="text-[10px] text-blue-900/60">Close</p>
                          <p className="metric-number text-lg">{branch.current_metrics?.closings || 0}</p>
                        </div>
                        <div className="rounded-xl bg-white/70 p-2">
                          <p className="text-[10px] text-blue-900/60">Ready</p>
                          <p className="metric-number text-lg">{readiness}%</p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {activeBranch && (
            <div className="grid min-h-0 gap-3 lg:grid-cols-2">
              <Card className="min-h-0">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-black tracking-tighter text-slate-900">
                    <Briefcase className="h-4 w-4 text-slate-700" />
                    {activeBranch.name}
                  </CardTitle>
                  <p className="text-[11px] text-blue-900/60">Executive snapshot unit terpilih.</p>
                </CardHeader>
                <CardContent className="space-y-3 p-4 pt-0">
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-2xl bg-white/75 p-2.5">
                      <Target className="mx-auto mb-1 h-3.5 w-3.5 text-slate-700" />
                      <p className="text-[10px] text-blue-900/60">Leads</p>
                      <p className="metric-number text-xl">{activeBranch.current_metrics?.leads || 0}</p>
                    </div>
                    <div className="rounded-2xl bg-white/75 p-2.5">
                      <CheckCircle2 className="mx-auto mb-1 h-3.5 w-3.5 text-slate-700" />
                      <p className="text-[10px] text-blue-900/60">Closings</p>
                      <p className="metric-number text-xl">{activeBranch.current_metrics?.closings || 0}</p>
                    </div>
                    <div className="rounded-2xl bg-white/75 p-2.5">
                      <TrendingUp className="mx-auto mb-1 h-3.5 w-3.5 text-slate-700" />
                      <p className="text-[10px] text-blue-900/60">Revenue</p>
                      <p className="metric-number text-xl">{formatCurrency(activeBranch.current_metrics?.revenue || 0)}</p>
                    </div>
                  </div>

                  <div>
                    <div className="mb-1 flex items-center justify-between text-[11px] font-semibold text-blue-900/60">
                      <span>Pipeline Maturity</span>
                      <span>{pipelineMaturity}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-white/70">
                      <div className="h-full rounded-full bg-slate-900" style={{ width: `${pipelineMaturity}%` }} />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="min-h-0">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-black tracking-tighter text-slate-900">
                    <MessageSquareQuote className="h-4 w-4 text-slate-700" />
                    CEO Executive Briefing
                  </CardTitle>
                  <p className="text-[11px] text-blue-900/60">Ringkasan terbaru yang sudah disanitasi untuk display publik.</p>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <p className="max-h-[140px] overflow-hidden text-sm leading-relaxed text-slate-900">{latestCeoMessage}</p>
                </CardContent>
              </Card>
            </div>
          )}
        </div>

        <Card className="flex min-h-0 flex-col">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg font-black tracking-tighter text-slate-900">
              <Bot className="h-5 w-5 text-slate-700" />
              Executive Boardroom
            </CardTitle>
            <p className="text-[11px] text-blue-900/60">Percakapan strategis real-time antara Chairman dan CEO.</p>
          </CardHeader>
          <CardContent className="no-scrollbar flex-1 space-y-2 overflow-y-auto p-4 pt-0">
            {sanitizedChatHistory.length === 0 && (
              <div className="rounded-2xl border border-white bg-white/70 p-4 text-sm text-blue-900/60">
                Belum ada percakapan boardroom.
              </div>
            )}
            {sanitizedChatHistory.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === "Chairman" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[92%] rounded-2xl border p-3 text-sm ${
                    msg.sender === "Chairman"
                      ? "border-sky-200/80 bg-sky-100 text-sky-700"
                      : "border-white bg-white/75 text-slate-900"
                  }`}
                >
                  <p className="mb-1 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-blue-900/60">
                    {msg.sender === "Chairman" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                    {msg.sender}
                  </p>
                  <p className="whitespace-pre-wrap break-words leading-relaxed">{msg.text}</p>
                </div>
              </div>
            ))}
          </CardContent>
          <div className="border-t border-white/90 p-3">
            <form onSubmit={handleSendMandate} className="relative">
              <Input
                placeholder="Ketik mandat chairman..."
                value={mandateText}
                onChange={(e) => setMandateText(e.target.value)}
                className="h-11 rounded-2xl border-white bg-white/80 pr-12 text-slate-900 placeholder:text-blue-900/50"
              />
              <Button
                type="submit"
                disabled={mandateMutation.isPending || !mandateText.trim()}
                className="absolute right-1.5 top-1.5 h-8.5 w-8.5 rounded-xl border border-slate-900 bg-slate-900 p-0 text-white hover:bg-slate-800"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </Card>
      </section>

      <footer className="glass-island shrink-0 flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-[11px] font-semibold text-blue-900/60">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-slate-700" />
            Ops heartbeat setiap 3 detik
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-slate-700" />
            Refresh branches setiap 5 detik
          </span>
        </div>
        <div>SPIO Sovereign OS v1.0</div>
      </footer>
    </div>
  );
}