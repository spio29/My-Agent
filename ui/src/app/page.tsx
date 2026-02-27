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
  if (status === "active") return "bg-emerald-500/15 text-emerald-300 border-emerald-500/35";
  if (status === "paused") return "bg-amber-500/15 text-amber-300 border-amber-500/35";
  return "bg-rose-500/15 text-rose-300 border-rose-500/35";
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
    <div className="ux-rise-in relative mx-auto max-w-[1600px] space-y-6 pb-8">
      <section className="relative overflow-hidden rounded-3xl border border-border/70 bg-card/70 shadow-[0_18px_60px_-38px_hsl(var(--primary)/0.65)]">
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute -right-20 -top-24 h-64 w-64 rounded-full bg-primary/20 blur-3xl" />
          <div className="absolute left-10 top-24 h-44 w-44 rounded-full bg-cyan-400/10 blur-3xl" />
        </div>
        <div className="relative space-y-6 p-6 md:p-8">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-2">
              <p className="inline-flex items-center gap-2 rounded-full border border-primary/35 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                <ShieldCheck className="h-3.5 w-3.5" />
                Live Executive Dashboard
              </p>
              <div className="flex items-center gap-3">
                <div className="rounded-2xl bg-primary/90 p-3 text-primary-foreground shadow-lg shadow-primary/25">
                  <Building2 className="h-6 w-6" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold tracking-tight text-foreground md:text-3xl">Sovereign Cockpit</h1>
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
                  className="rounded-xl border border-border/60 bg-background/35 px-3 py-2 text-xs font-semibold text-muted-foreground"
                >
                  <p className="mb-1 flex items-center gap-2 uppercase tracking-wide">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        item.state === "online"
                          ? "bg-emerald-400"
                          : item.state === "attention"
                            ? "bg-amber-400"
                            : "bg-slate-400"
                      }`}
                    />
                    {item.label}
                  </p>
                  <p className="text-sm text-foreground">{item.value}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Card className="border-border/60 bg-background/35">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Total Revenue</p>
                <p className="text-2xl font-bold text-emerald-300">{formatCurrency(totalRevenue)}</p>
                <p className="mt-1 flex items-center gap-1 text-xs text-emerald-300/90">
                  <TrendingUp className="h-3.5 w-3.5" />
                  Across all active branches
                </p>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-background/35">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Active Units</p>
                <p className="text-2xl font-bold text-foreground">{activeUnits}</p>
                <p className="mt-1 text-xs text-muted-foreground">{branches.length} units terdaftar</p>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-background/35">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Pipeline Leads</p>
                <p className="text-2xl font-bold text-cyan-300">{totalLeads}</p>
                <p className="mt-1 text-xs text-muted-foreground">Total leads yang masuk ke funnel</p>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-background/35">
              <CardContent className="p-4">
                <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Operational Readiness</p>
                <p className="text-2xl font-bold text-foreground">{readinessAverage}%</p>
                <div className="mt-2 h-2 w-full rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${readinessAverage}%` }} />
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <div className="space-y-6">
          <Card className="overflow-hidden border-border/70 bg-card/70">
            <CardHeader className="border-b border-border/60 pb-4">
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
                          ? "border-primary/70 bg-primary/10 shadow-[0_0_0_1px_hsl(var(--primary)/0.3)]"
                          : "border-border/60 bg-background/35 hover:border-primary/45 hover:bg-background/55"
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
                        <div className="rounded-lg bg-muted/45 p-2">
                          <p className="text-muted-foreground">Leads</p>
                          <p className="mt-1 font-semibold text-foreground">{branch.current_metrics?.leads || 0}</p>
                        </div>
                        <div className="rounded-lg bg-muted/45 p-2">
                          <p className="text-muted-foreground">Closings</p>
                          <p className="mt-1 font-semibold text-foreground">{branch.current_metrics?.closings || 0}</p>
                        </div>
                        <div className="rounded-lg bg-muted/45 p-2">
                          <p className="text-muted-foreground">Revenue</p>
                          <p className="mt-1 font-semibold text-foreground">{formatCurrency(branch.current_metrics?.revenue || 0)}</p>
                        </div>
                      </div>
                      <div>
                        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
                          <span>Readiness</span>
                          <span>{readiness}%</span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${readiness}%` }} />
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
              <Card className="border-border/70 bg-card/70">
                <CardHeader className="pb-4">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <Briefcase className="h-5 w-5 text-primary" />
                    {activeBranch.name}
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">Executive snapshot untuk unit terpilih.</p>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="rounded-xl bg-muted/45 p-3">
                      <Target className="mx-auto mb-1.5 h-4 w-4 text-primary" />
                      <p className="text-xs text-muted-foreground">Leads</p>
                      <p className="text-xl font-semibold">{activeBranch.current_metrics?.leads || 0}</p>
                    </div>
                    <div className="rounded-xl bg-muted/45 p-3">
                      <CheckCircle2 className="mx-auto mb-1.5 h-4 w-4 text-emerald-300" />
                      <p className="text-xs text-muted-foreground">Closings</p>
                      <p className="text-xl font-semibold">{activeBranch.current_metrics?.closings || 0}</p>
                    </div>
                    <div className="rounded-xl bg-muted/45 p-3">
                      <TrendingUp className="mx-auto mb-1.5 h-4 w-4 text-cyan-300" />
                      <p className="text-xs text-muted-foreground">Revenue</p>
                      <p className="text-xl font-semibold">{formatCurrency(activeBranch.current_metrics?.revenue || 0)}</p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Pipeline Maturity</span>
                      <span>{Math.min(100, (activeBranch.current_metrics?.closings || 0) > 0 ? 100 : (activeBranch.current_metrics?.leads || 0) > 0 ? 60 : 25)}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-muted">
                      <div
                        className="h-full rounded-full bg-gradient-to-r from-primary to-cyan-300"
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

              <Card className="relative overflow-hidden border-border/70 bg-card/70">
                <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-primary/15 blur-3xl" />
                <CardHeader className="pb-4">
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <MessageSquareQuote className="h-5 w-5 text-primary" />
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

        <Card className="flex max-h-[82vh] flex-col overflow-hidden border-border/70 bg-card/70 xl:sticky xl:top-24">
          <CardHeader className="border-b border-border/60">
            <CardTitle className="flex items-center gap-2 text-lg">
              <Bot className="h-5 w-5 text-primary" />
              Executive Boardroom
            </CardTitle>
            <p className="text-sm text-muted-foreground">Percakapan strategis real-time antara Chairman dan CEO.</p>
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto space-y-4 p-4">
            {sanitizedChatHistory.length === 0 && (
              <div className="rounded-xl border border-dashed border-border/60 bg-muted/25 p-4 text-sm text-muted-foreground">
                Belum ada percakapan boardroom.
              </div>
            )}
            {sanitizedChatHistory.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === "Chairman" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[90%] rounded-2xl border p-3 text-sm ${
                    msg.sender === "Chairman"
                      ? "border-primary/45 bg-primary/15 text-foreground"
                      : "border-border/60 bg-background/35 text-foreground"
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
          <div className="border-t border-border/60 bg-background/25 p-4">
            <form onSubmit={handleSendMandate} className="relative">
              <Input
                placeholder="Ketik mandat chairman..."
                value={mandateText}
                onChange={(e) => setMandateText(e.target.value)}
                className="h-12 rounded-xl border-border/70 bg-card pr-12"
              />
              <Button
                type="submit"
                disabled={mandateMutation.isPending || !mandateText.trim()}
                className="absolute right-1.5 top-1.5 h-9 w-9 rounded-lg p-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
          </div>
        </Card>
      </section>

      <footer className="sticky bottom-0 z-20 w-full rounded-2xl border border-border/50 bg-card/90 px-4 py-3 text-xs font-semibold text-muted-foreground backdrop-blur-md sm:flex sm:items-center sm:justify-between sm:px-6">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-primary" />
            Ops heartbeat setiap 3 detik
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-cyan-300" />
            Refresh branches setiap 5 detik
          </span>
        </div>
        <div className="mt-1 sm:mt-0">SPIO Sovereign OS v1.0</div>
      </footer>
    </div>
  );
}
