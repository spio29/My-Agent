"use client";

import Link from "next/link";
import { useMemo, useState, useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { 
  Building2, 
  TrendingUp, 
  Target, 
  Zap, 
  CheckCircle2,
  Briefcase,
  AlertCircle,
  MessageSquareQuote,
  ArrowUpRight,
  ArrowRight,
  Send,
  Bot,
  User,
  Activity,
  ShieldCheck
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { 
  getBranches, 
  getBoardroomHistory, 
  sendChairmanMandate, 
  getSystemInfrastructure,
  type Branch, 
  type ChatMessage 
} from "@/lib/api";

const formatCurrency = (val: number) => {
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0
  }).format(val);
};

const sanitizeBoardroomText = (text: string) => {
  return text
    .replace(/<think>[\s\S]*?<\/think>/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
};

export default function ChairmanDashboard() {
  const queryClient = useQueryClient();
  const [activeBranchId, setActiveBranchId] = useState<string | null>(null);
  const [mandateText, setMandateText] = useState("");
  const chatEndRef = useRef<HTMLDivElement>(null);

  const { data: branches = [], isLoading: isLoadingBranches } = useQuery({
    queryKey: ["branches"],
    queryFn: getBranches,
    refetchInterval: 5000,
  });

  const { data: infra = {}, isLoading: isLoadingInfra } = useQuery({
    queryKey: ["system-infra"],
    queryFn: getSystemInfrastructure,
    refetchInterval: 3000,
  });

  const { data: chatHistory = [], isLoading: isLoadingChat } = useQuery({
    queryKey: ["boardroom-chat"],
    queryFn: getBoardroomHistory,
    refetchInterval: 3000,
  });

  const mandateMutation = useMutation({
    mutationFn: sendChairmanMandate,
    onSuccess: () => {
      setMandateText("");
      queryClient.invalidateQueries({ queryKey: ["boardroom-chat"] });
    }
  });

  const totalRevenue = useMemo(() => 
    branches.reduce((sum, b) => sum + (b.current_metrics?.revenue || 0), 0)
  , [branches]);

  const totalClosings = useMemo(() => 
    branches.reduce((sum, b) => sum + (b.current_metrics?.closings || 0), 0)
  , [branches]);

  const activeBranch = useMemo(() => 
    branches.find(b => b.branch_id === activeBranchId)
  , [branches, activeBranchId]);

  const sanitizedChatHistory = useMemo(() => 
    chatHistory
      .map((msg) => {
        const cleanedText = msg.sender === "CEO" ? sanitizeBoardroomText(msg.text) : msg.text.trim();
        return { ...msg, text: cleanedText };
      })
      .filter((msg) => msg.text.length > 0)
  , [chatHistory]);

  const latestCeoMessage = useMemo(() => {
    const ceoMsgs = [...sanitizedChatHistory].reverse().filter(m => m.sender === "CEO");
    return ceoMsgs[0]?.text || "Menunggu laporan pertama dari CEO...";
  }, [sanitizedChatHistory]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
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

  const handleSendMandate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!mandateText.trim()) return;
    mandateMutation.mutate(mandateText);
  };

  return (
    <div className="ux-rise-in space-y-6 max-w-[1600px] mx-auto pb-10">
      {/* Top Banner: Metrics & Identity */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-6 py-4 px-4 bg-card border-b border-border/50 sticky top-0 z-20 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-2xl bg-primary flex items-center justify-center text-white shadow-xl shadow-primary/20">
            <Building2 className="h-7 w-7" />
          </div>
          <div>
            <h1 className="text-2xl font-black tracking-tight text-foreground">Sovereign Cockpit</h1>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground opacity-60">Chairman Command Center</p>
          </div>
        </div>

        <div className="flex items-center gap-8 px-6 py-2 rounded-2xl bg-muted/30 border border-border/50">
          <div className="text-center">
            <p className="text-[9px] font-bold text-muted-foreground uppercase mb-1">Portfolio Profit</p>
            <p className="text-2xl font-black text-emerald-500 tracking-tight">{formatCurrency(totalRevenue)}</p>
          </div>
          <div className="h-8 w-px bg-border/60"></div>
          <div className="text-center">
            <p className="text-[9px] font-bold text-muted-foreground uppercase mb-1">Units Active</p>
            <p className="text-2xl font-black text-primary tracking-tight">{branches.length}</p>
          </div>
          <div className="h-8 w-px bg-border/60"></div>
          <div className="text-center">
            <p className="text-[9px] font-bold text-muted-foreground uppercase mb-1">Closings</p>
            <p className="text-2xl font-black text-foreground tracking-tight">{totalClosings}</p>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 px-2">
        
        {/* Central Intelligence */}
        <div className="lg:col-span-8 space-y-8">
          
          {/* Business Units */}
          <div className="space-y-4">
            <h2 className="text-xs font-bold uppercase tracking-widest text-muted-foreground px-2">Strategic Business Units</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {branches.map((b) => (
                <button
                  key={b.branch_id}
                  onClick={() => setActiveBranchId(b.branch_id)}
                  className={`text-left transition-all duration-500 rounded-3xl ${
                    activeBranchId === b.branch_id ? "ring-2 ring-primary ring-offset-4 ring-offset-background" : ""
                  }`}
                >
                  <Card className={`overflow-hidden rounded-3xl border-none shadow-sm transition-all duration-300 ${
                    activeBranchId === b.branch_id ? "bg-primary text-white" : "bg-card hover:bg-muted/50"
                  }`}>
                    <CardContent className="p-5 flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={`p-3 rounded-2xl ${activeBranchId === b.branch_id ? "bg-white/20" : "bg-muted"}`}>
                          <Briefcase className="h-5 w-5" />
                        </div>
                        <div>
                          <p className="font-black text-sm">{b.name}</p>
                          <p className={`text-[10px] font-bold ${activeBranchId === b.branch_id ? "text-white/70" : "text-emerald-500"}`}>
                            {formatCurrency(b.current_metrics?.revenue || 0)}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <div className={`h-2 w-2 rounded-full ${b.status === "active" ? (activeBranchId === b.branch_id ? "bg-white animate-pulse" : "bg-emerald-500 animate-pulse") : "bg-muted"}`}></div>
                        {(!b.operational_ready || Object.keys(b.operational_ready).length === 0) && (
                          <span className="text-[8px] font-bold text-rose-500 animate-bounce">NO AMMO</span>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </button>
              ))}
            </div>
          </div>

          {/* Detailed Performance */}
          {activeBranch && (
            <div className="space-y-6 animate-in fade-in zoom-in-95 duration-700">
              <div className="grid grid-cols-3 gap-6">
                {[
                  { label: "LEADS", value: activeBranch.current_metrics.leads, icon: Target, color: "text-primary" },
                  { label: "CLOSINGS", value: activeBranch.current_metrics.closings, icon: CheckCircle2, color: "text-emerald-500" },
                  { label: "STATUS", value: activeBranch.status.toUpperCase(), icon: Activity, color: "text-blue-500" }
                ].map((stat, i) => (
                  <Card key={i} className="rounded-[2rem] border-none shadow-none bg-card p-6 text-center">
                    <stat.icon className={`h-5 w-5 mx-auto mb-2 ${stat.color}`} />
                    <p className="text-[10px] font-black text-muted-foreground uppercase tracking-widest">{stat.label}</p>
                    <p className="text-3xl font-black mt-1 tracking-tight">{stat.value}</p>
                  </Card>
                ))}
              </div>

              {/* CEO Dynamic Briefing */}
              <div className="p-6 rounded-[2rem] bg-primary/5 border border-primary/20 relative overflow-hidden">
                <MessageSquareQuote className="absolute -right-2 -bottom-2 h-24 w-24 opacity-5" />
                <p className="text-[10px] font-bold uppercase tracking-widest text-primary mb-3 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse"></span>
                  CEO Executive Briefing
                </p>
                <p className="text-sm text-foreground leading-relaxed italic font-medium">
                  &quot;{latestCeoMessage}&quot;
                </p>
              </div>

              {/* Pipeline */}
              <Card className="rounded-[2.5rem] border-none shadow-sm bg-card p-10">
                <div className="relative flex items-center justify-between px-10">
                  <div className="absolute h-0.5 w-[85%] bg-muted/40 left-1/2 -translate-x-1/2 top-6 -z-0 rounded-full"></div>
                  {[
                    { label: "RESEARCH", icon: Zap, active: true },
                    { label: "PROMOTION", icon: Target, active: activeBranch.current_metrics.leads > 0 },
                    { label: "CLOSING", icon: CheckCircle2, active: activeBranch.current_metrics.closings > 0 }
                  ].map((step, i) => (
                    <div key={i} className="z-10 flex flex-col items-center gap-4">
                      <div className={`h-12 w-12 rounded-2xl flex items-center justify-center transition-all duration-700 shadow-xl ${
                        step.active ? "bg-primary text-white scale-125" : "bg-muted text-muted-foreground opacity-40"
                      }`}>
                        <step.icon className="h-6 w-6" />
                      </div>
                      <p className={`text-[10px] font-black tracking-widest ${step.active ? "text-foreground" : "text-muted-foreground"}`}>{step.label}</p>
                    </div>
                  ))}
                </div>
              </Card>
            </div>
          )}
        </div>

        {/* Executive Boardroom */}
        <div className="lg:col-span-4 flex flex-col h-[85vh] sticky top-24">
          <Card className="rounded-[2.5rem] border-none shadow-2xl shadow-primary/5 bg-card flex flex-col h-full overflow-hidden border border-primary/10">
            <CardHeader className="border-b border-border/50 py-6 bg-gradient-to-r from-primary/5 to-transparent">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 rounded-2xl bg-primary flex items-center justify-center text-white shadow-lg shadow-primary/30">
                  <Bot className="h-7 w-7" />
                </div>
                <div>
                  <CardTitle className="text-lg font-black tracking-tight">Executive Boardroom</CardTitle>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest">CEO Online</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="flex-1 overflow-y-auto p-6 space-y-6 custom-scrollbar">
              {sanitizedChatHistory.map((msg) => (
                <div key={msg.id} className={`flex ${msg.sender === "Chairman" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[90%] rounded-3xl p-4 text-sm shadow-sm ${
                    msg.sender === "Chairman" 
                      ? "bg-primary text-primary-foreground rounded-tr-none" 
                      : "bg-muted/50 text-foreground rounded-tl-none border border-border/50"
                  }`}>
                    <div className="flex items-center gap-2 mb-2 opacity-60">
                      {msg.sender === "Chairman" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                      <span className="font-black text-[10px] uppercase tracking-tighter">{msg.sender}</span>
                    </div>
                    <p className="leading-relaxed font-medium">{msg.text}</p>
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </CardContent>
            <div className="p-6 bg-muted/10 border-t border-border/50">
              <form onSubmit={handleSendMandate} className="relative">
                <Input 
                  placeholder="Ketik Mandat Chairman..."
                  value={mandateText}
                  onChange={(e) => setMandateText(e.target.value)}
                  className="pr-14 h-14 rounded-2xl border-border bg-card shadow-inner"
                />
                <Button type="submit" className="absolute right-2 top-2 h-10 w-10 rounded-xl p-0">
                  <Send className="h-5 w-5" />
                </Button>
              </form>
            </div>
          </Card>
        </div>
      </div>

      {/* Health Beacon Footer */}
      <footer className="sticky bottom-0 z-20 mt-4 w-full rounded-2xl border border-border/50 bg-card/90 px-4 py-2 text-[10px] font-bold tracking-widest text-muted-foreground backdrop-blur-md sm:flex sm:items-center sm:justify-between sm:px-6">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
          <div className="flex items-center gap-2">
            <div className={`h-1.5 w-1.5 rounded-full ${infra.api?.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`}></div>
            <span>API: {infra.api?.status?.toUpperCase() || "CHECKING"}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`h-1.5 w-1.5 rounded-full ${infra.redis?.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`}></div>
            <span>REDIS: {infra.redis?.memory_used || "OFFLINE"}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`h-1.5 w-1.5 rounded-full ${infra.ai_factory?.status === "ready" ? "bg-emerald-500" : "bg-amber-500"}`}></div>
            <span>AI FACTORY: {infra.ai_factory?.status?.toUpperCase() || "NOT CONFIGURED"}</span>
          </div>
        </div>
        <div className="mt-1 flex items-center gap-2 sm:mt-0 sm:justify-end">
          <Activity className="h-3 w-3" />
          <span>SPIO SOVEREIGN OS v1.0</span>
        </div>
      </footer>
    </div>
  );
}
