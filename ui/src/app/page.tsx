"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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
  if (status === "active") return "bg-sky-100 text-sky-700 border-sky-200/70";
  if (status === "paused") return "bg-slate-100 text-slate-500 border-slate-200/80";
  return "bg-slate-100 text-slate-500 border-slate-200/80";
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
  const chatEndRef = useRef<HTMLDivElement>(null);

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
  const totalClosings = useMemo(
    () => branches.reduce((sum, branch) => sum + (branch.current_metrics?.closings || 0), 0),
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

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sanitizedChatHistory]);

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

  return (
    <div className="ux-rise-in relative mx-auto max-w-[1600px] space-y-6 pb-8 text-slate-900">
      <section className="relative overflow-hidden rounded-2xl border border-slate-200/60 bg-white shadow-sm">
        <div className="pointer-events-none absolute inset-0 hidden">
          <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-slate-100 blur-3xl" />
          <div className="absolute left-10 top-24 h-44 w-44 rounded-full bg-accent/28 blur-3xl" />
        </div>
        <div className="relative space-y-6 p-6 md:p-8">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-2">
              <p className="inline-flex items-center gap-2 rounded-full border border-sky-200/70 bg-sky-100 px-3 py-1 text-xs font-semibold text-sky-700">
                <ShieldCheck className="h-3.5 w-3.5" />
                Live Executive Dashboard
              </p>
              <div className="flex items-center gap-3">
                <div className="rounded-xl border border-slate-200/60 bg-slate-50 p-3 text-slate-900 shadow-sm">
                  <Building2 className="h-6 w-6" />
                </div>
                <div>
                  <h1 className="text-2xl font-extrabold tracking-tight text-slate-900 md:text-3xl">Sovereign Cockpit</h1>
                  <p className="text-sm text-muted-foreground">
                    Command center untuk memonitor pertumbuhan, operasi, dan eksekusi mandatori cabang.
                  </p>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {healthItems.map((item) => (
                <div
                  key={item.label}
                  className={`rounded-xl border px-3 py-2 text-xs font-semibold ${item.state === "online" ? "border-sky-200/70 bg-sky-100 text-sky-700" : "border-slate-200/60 bg-white text-slate-500"}`}
                >
                  <p className="mb-1 flex items-center gap-2 uppercase tracking-wide">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        item.state === "online"
                          ? "bg-sky-500"
                          : item.state === "attention"
                            ? "bg-amber-200"
                            : "bg-slate-300"
                      }`}
                    />
                    {item.label}
                  </p>
                  <p className={`text-sm ${item.state === "online" ? "text-sky-700" : "text-slate-900"}`}>{item.value}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Card className="rounded-2xl border-slate-200/60 bg-white shadow-sm">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Total Revenue</p>
                <p className="metric-number text-3xl text-slate-900">{formatCurrency(totalRevenue)}</p>
                <p className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                  <TrendingUp className="h-3.5 w-3.5" />
                  Across all active branches
                </p>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-slate-200/60 bg-white shadow-sm">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Active Units</p>
                <p className="metric-number text-3xl text-slate-900">{activeUnits}</p>
                <p className="mt-1 text-xs text-muted-foreground">{branches.length} units terdaftar</p>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-slate-200/60 bg-white shadow-sm">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Pipeline Leads</p>
                <p className="metric-number text-3xl text-slate-900">{totalLeads}</p>
                <p className="mt-1 text-xs text-muted-foreground">Total leads yang masuk ke funnel</p>
              </CardContent>
            </Card>

            <Card className="rounded-2xl border-slate-200/60 bg-white shadow-sm">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Operational Readiness</p>
                <p className="metric-number text-3xl text-slate-900">{readinessAverage}%</p>
                <div className="mt-2 h-2 w-full rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-slate-900 transition-all" style={{ width: `${readinessAverage}%` }} />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <Card className="overflow-hidden rounded-2xl border-slate-200/60 bg-white shadow-sm">
            <CardHeader className="border-b border-slate-200/60 pb-4">
              <CardTitle className="text-xl">Strategic Business Units</CardTitle>
              <p className="text-sm text-muted-foreground">Pantau performa setiap unit, pilih prioritas, dan eksekusi cepat.</p>
            </CardHeader>
            <CardContent className="p-5">
              <div className="grid gap-3 md:grid-cols-2">
                {branches.map((branch) => {
                  const readiness = getBranchReadiness(branch);
                  const isActive = branch.branch_id === activeBranchId;
                  return (
                    <button
                      key={branch.branch_id}
                      onClick={() => setActiveBranchId(branch.branch_id)}
                      className={`rounded-2xl border p-4 text-left transition-all ${
                        isActive
                          ? "border-sky-200/70 bg-sky-100 shadow-sm"
                          : "border-slate-200/70 bg-white hover:border-slate-300 hover:bg-slate-50"
                      }`}
                    >
                      <div className="mb-3 flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-foreground">{branch.name}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{branch.branch_id}</p>
                        </div>
                        <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${getStatusStyle(branch.status)}`}>
                          {branch.status.toUpperCase()}
                        </span>
                      </div>
                      <div className="mb-3 grid grid-cols-3 gap-2 text-xs">
                        <div className="rounded-lg bg-slate-50 p-2">
                          <p className="text-muted-foreground">Leads</p>
                          <p className="mt-1 font-semibold text-foreground">{branch.current_metrics?.leads || 0}</p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-2">
                          <p className="text-muted-foreground">Closings</p>
                          <p className="mt-1 font-semibold text-foreground">{branch.current_metrics?.closings || 0}</p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-2">
                          <p className="text-muted-foreground">Revenue</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCurrency(branch.current_metrics?.revenue || 0)}</p>
                        </div>
                      </div>
                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                          <span>Readiness</span>
                          <span>{readiness}%</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-slate-100">
                          <div className="h-full rounded-full bg-slate-900 transition-all" style={{ width: `${readiness}%` }} />
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {activeBranch && (
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
              <Card className="rounded-2xl border-slate-200/60 bg-white shadow-sm">
                <CardHeader className="pb-4">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Briefcase className="h-5 w-5 text-slate-700" />
                    {activeBranch.name}
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">Executive snapshot untuk unit terpilih.</p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="rounded-xl bg-slate-50 p-3">
                      <Target className="mx-auto mb-1.5 h-4 w-4 text-slate-700" />
                      <p className="text-xs text-muted-foreground">Leads</p>
                      <p className="metric-number text-2xl">{activeBranch.current_metrics?.leads || 0}</p>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3">
                      <CheckCircle2 className="mx-auto mb-1.5 h-4 w-4 text-slate-700" />
                      <p className="text-xs text-muted-foreground">Closings</p>
                      <p className="metric-number text-2xl">{activeBranch.current_metrics?.closings || 0}</p>
                    </div>
                    <div className="rounded-xl bg-slate-50 p-3">
                      <TrendingUp className="mx-auto mb-1.5 h-4 w-4 text-slate-700" />
                      <p className="text-xs text-muted-foreground">Revenue</p>
                      <p className="metric-number text-2xl">{formatCurrency(activeBranch.current_metrics?.revenue || 0)}</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Pipeline Maturity</span>
                      <span>{Math.min(100, (activeBranch.current_metrics?.closings || 0) > 0 ? 100 : (activeBranch.current_metrics?.leads || 0) > 0 ? 60 : 25)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-slate-900"
                        style={{
                          width: `${Math.min(
                            100,
                            (activeBranch.current_metrics?.closings || 0) > 0
                              ? 100
                              : (activeBranch.current_metrics?.leads || 0) > 0
                                ? 60
                                : 25,
                          )}%`,
                        }}
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="relative overflow-hidden rounded-2xl border-slate-200/60 bg-white shadow-sm">
                <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-slate-100 blur-3xl" />
                <CardHeader className="pb-4">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <MessageSquareQuote className="h-5 w-5 text-slate-700" />
                    CEO Executive Briefing
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">Ringkasan terkini yang sudah disanitasi untuk display publik.</p>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground/95">{latestCeoMessage}</p>
                </CardContent>
              </Card>
            </div>
          )}
        </div>

        <Card className="flex max-h-[82vh] flex-col overflow-hidden rounded-2xl border-slate-200/60 bg-white shadow-sm xl:sticky xl:top-24">
          <CardHeader className="border-b border-slate-200/60">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Bot className="h-5 w-5 text-slate-700" />
              Executive Boardroom
            </CardTitle>
            <p className="text-sm text-muted-foreground">Percakapan strategis real-time antara Chairman dan CEO.</p>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto space-y-4 p-4">
            {sanitizedChatHistory.length === 0 && (
              <div className="rounded-xl border border-dashed border-slate-200/80 bg-slate-50 p-4 text-sm text-muted-foreground">
                Belum ada percakapan boardroom.
              </div>
            )}
            {sanitizedChatHistory.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === "Chairman" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[90%] rounded-2xl border p-3 text-sm ${
                    msg.sender === "Chairman"
                      ? "border-sky-200/70 bg-sky-100 text-sky-700"
                      : "border-slate-200/70 bg-white text-slate-900"
                  }`}
                >
                  <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {msg.sender === "Chairman" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                    {msg.sender}
                  </p>
                  <p className="whitespace-pre-wrap break-words leading-relaxed">{msg.text}</p>
                </div>
              </div>
            ))}
            <div ref={chatEndRef} />
          </CardContent>
          <div className="border-t border-slate-200/60 bg-white p-4">
            <form onSubmit={handleSendMandate} className="relative">
              <Input
                placeholder="Ketik mandat chairman..."
                value={mandateText}
                onChange={(e) => setMandateText(e.target.value)}
                className="h-12 rounded-xl border-slate-200/80 bg-white pr-12 text-slate-900 placeholder:text-slate-500"
              />
              <Button
                type="submit"
                disabled={mandateMutation.isPending || !mandateText.trim()}
                className="absolute right-1.5 top-1.5 h-9 w-9 rounded-lg border border-slate-900 bg-slate-900 p-0 text-white hover:bg-slate-800"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </Card>
      </section>

      <footer className="sticky bottom-0 z-20 w-full rounded-2xl border border-slate-200/60 bg-white px-4 py-3 text-xs font-semibold text-slate-500 sm:flex sm:items-center sm:justify-between sm:px-6">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-slate-700" />
            Ops heartbeat setiap 3 detik
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-slate-700" />
            Refresh branches setiap 5 detik
          </span>
        </div>
        <div className="mt-1 sm:mt-0">SPIO Sovereign OS v1.0</div>
      </footer>
    </div>
  );
}
