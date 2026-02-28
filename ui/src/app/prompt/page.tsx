"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Loader2, PlayCircle, SlidersHorizontal, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { executePlannerPrompt, getIntegrationAccounts, type PlannerExecuteResponse } from "@/lib/api";

type PromptTemplate = {
  id: string;
  label: string;
  hint: string;
  prompt: string;
};

const PROMPT_TEMPLATES: PromptTemplate[] = [
  {
    id: "monitor-report-telegram",
    label: "Monitor + Report",
    hint: "Telegram tiap 30 detik + laporan harian.",
    prompt: "Pantau telegram akun bot_a01 tiap 30 detik dan buat laporan harian jam 07:00.",
  },
  {
    id: "monitor-report-whatsapp",
    label: "WA Ops + Report",
    hint: "WhatsApp ops + laporan pagi jam 08:00.",
    prompt: "Pantau whatsapp akun ops_01 tiap 45 detik dan buat laporan harian jam 08:00.",
  },
  {
    id: "report-backup",
    label: "Report + Backup",
    hint: "Laporan + backup harian dengan jadwal terpisah.",
    prompt: "Buat laporan harian jam 07:30 dan backup harian jam 01:30.",
  },
  {
    id: "workflow-github-notion",
    label: "Workflow MCP",
    hint: "Sinkron issue GitHub ke Notion workspace ops.",
    prompt: "Sinkron issue terbaru dari github ke notion workspace ops.",
  },
];

const clampWaitSeconds = (value: number) => {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(30, Math.floor(value)));
};

const getCreateStatusLabel = (status: "created" | "updated" | "error") => {
  if (status === "created") return "Dibuat";
  if (status === "updated") return "Diperbarui";
  return "Error";
};

const getCreateStatusClass = (status: "created" | "updated" | "error") => {
  if (status === "created") return "status-baik";
  if (status === "updated") return "status-netral";
  return "status-buruk";
};

const getRunStatusLabel = (status?: "queued" | "running" | "success" | "failed") => {
  if (status === "queued") return "Antre";
  if (status === "running") return "Berjalan";
  if (status === "success") return "Berhasil";
  if (status === "failed") return "Gagal";
  return "-";
};

const getRunStatusClass = (status?: "queued" | "running" | "success" | "failed") => {
  if (status === "success") return "status-baik";
  if (status === "failed") return "status-buruk";
  if (status === "running") return "status-waspada";
  return "status-netral";
};

export default function PromptPage() {
  const queryClient = useQueryClient();

  const [prompt, setPrompt] = useState(PROMPT_TEMPLATES[0].prompt);
  const [useAi, setUseAi] = useState(false);
  const [runImmediately, setRunImmediately] = useState(true);
  const [waitSeconds, setWaitSeconds] = useState(2);
  const [forceRuleBased, setForceRuleBased] = useState(true);
  const [timezone, setTimezone] = useState("Asia/Jakarta");
  const [aiProvider, setAiProvider] = useState("auto");
  const [aiAccountId, setAiAccountId] = useState("default");
  const [result, setResult] = useState<PlannerExecuteResponse | null>(null);

  const { data: integrationAccounts = [] } = useQuery({
    queryKey: ["integration-accounts"],
    queryFn: () => getIntegrationAccounts(),
    refetchInterval: 10000,
  });

  const providerOptions = useMemo(() => {
    const options = new Set<string>(["auto", "openai", "ollama"]);
    for (const row of integrationAccounts) {
      const provider = String(row.provider || "").trim().toLowerCase();
      if (!provider) continue;
      options.add(provider);
    }
    return Array.from(options).sort((a, b) => a.localeCompare(b));
  }, [integrationAccounts]);

  const accountOptions = useMemo(() => {
    if (aiProvider === "auto") return ["default"];

    const options = new Set<string>(["default"]);
    for (const row of integrationAccounts) {
      const provider = String(row.provider || "").trim().toLowerCase();
      if (provider !== aiProvider) continue;
      const accountId = String(row.account_id || "").trim();
      if (!accountId) continue;
      options.add(accountId);
    }
    if (aiAccountId) options.add(aiAccountId);
    return Array.from(options).sort((a, b) => a.localeCompare(b));
  }, [integrationAccounts, aiProvider, aiAccountId]);

  const submitMutation = useMutation({
    mutationFn: executePlannerPrompt,
    onSuccess: (data) => {
      setResult(data);
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      toast.success("Perintah berhasil diproses.");
    },
    onError: () => {
      toast.error("Perintah gagal diproses.");
    },
  });

  const resultSummary = useMemo(() => {
    if (!result) return null;
    const total = result.results.length;
    const created = result.results.filter((item) => item.create_status === "created").length;
    const updated = result.results.filter((item) => item.create_status === "updated").length;
    const errored = result.results.filter((item) => item.create_status === "error").length;
    const runSuccess = result.results.filter((item) => item.run_status === "success").length;
    const runFailed = result.results.filter((item) => item.run_status === "failed").length;
    return { total, created, updated, errored, runSuccess, runFailed };
  }, [result]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const cleanPrompt = prompt.trim();
    if (!cleanPrompt) {
      toast.error("Perintah tidak boleh kosong.");
      return;
    }

    submitMutation.mutate({
      prompt: cleanPrompt,
      use_ai: useAi,
      force_rule_based: useAi ? forceRuleBased : false,
      ai_provider: useAi ? aiProvider : undefined,
      ai_account_id: useAi && aiProvider !== "auto" ? aiAccountId.trim() || "default" : undefined,
      openai_account_id: useAi && aiProvider === "openai" ? aiAccountId.trim() || "default" : undefined,
      run_immediately: runImmediately,
      wait_seconds: runImmediately ? clampWaitSeconds(waitSeconds) : 0,
      timezone,
    });
  };

  const plannerLabel = result?.planner_source === "smolagents" ? "AI" : "Rule-based";
  const plannerClass = result?.planner_source === "smolagents" ? "status-waspada" : "status-netral";

  return (
    <div className="ux-rise-in space-y-5">
      <section className="ux-fade-in-delayed rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-foreground">Jalankan Perintah</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Tulis satu instruksi, sistem akan ubah ke job lalu jalankan.
            </p>
          </div>
          <span className="inline-flex items-center gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-xs text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            Plan + Save + Run
          </span>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Form Perintah</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
              <p className="text-xs font-medium text-muted-foreground">Template Cepat</p>
              <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {PROMPT_TEMPLATES.map((item) => {
                  const isActive = prompt.trim() === item.prompt.trim();
                  return (
                    <button
                      key={item.id}
                      type="button"
                      disabled={submitMutation.isPending}
                      onClick={() => setPrompt(item.prompt)}
                      className={`rounded-lg border p-3 text-left transition ${
                        isActive
                          ? "border-primary bg-primary/10"
                          : "border-border bg-card hover:border-primary/40 hover:bg-muted/30"
                      }`}
                    >
                      <p className="text-sm font-medium">{item.label}</p>
                      <p className="mt-1 text-xs text-muted-foreground">{item.hint}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="prompt">Isi Perintah</Label>
              <Textarea
                id="prompt"
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                className="min-h-[120px]"
                placeholder="Contoh: Pantau telegram akun bot_a01 tiap 30 detik dan buat laporan harian jam 07:00."
                disabled={submitMutation.isPending}
              />
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">Gunakan AI</p>
                    <p className="text-xs text-muted-foreground">Planner pakai AI bila tersedia.</p>
                  </div>
                  <Switch checked={useAi} disabled={submitMutation.isPending} onCheckedChange={setUseAi} />
                </div>
              </div>
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">Jalankan Langsung</p>
                    <p className="text-xs text-muted-foreground">Hasil plan langsung masuk antrean run.</p>
                  </div>
                  <Switch
                    checked={runImmediately}
                    disabled={submitMutation.isPending}
                    onCheckedChange={(checked) => {
                      setRunImmediately(checked);
                      if (!checked) setWaitSeconds(0);
                      if (checked && waitSeconds === 0) setWaitSeconds(2);
                    }}
                  />
                </div>
              </div>
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <Label htmlFor="wait-seconds" className="text-sm font-medium">
                  Tunggu hasil (detik)
                </Label>
                <Input
                  id="wait-seconds"
                  type="number"
                  min={0}
                  max={30}
                  value={waitSeconds}
                  onChange={(event) => setWaitSeconds(clampWaitSeconds(Number(event.target.value)))}
                  disabled={!runImmediately || submitMutation.isPending}
                  className="mt-1"
                />
              </div>
            </div>

            <details className="rounded-lg border border-border bg-muted/20 p-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium">
                <SlidersHorizontal className="h-4 w-4" />
                Opsi Lanjutan
              </summary>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-lg border border-border bg-card p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium">Paksa Rule-based</p>
                      <p className="text-xs text-muted-foreground">AI dilewati kalau ini aktif.</p>
                    </div>
                    <Switch
                      checked={forceRuleBased}
                      onCheckedChange={setForceRuleBased}
                      disabled={!useAi || submitMutation.isPending}
                    />
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-card p-3">
                  <Label htmlFor="timezone">Timezone</Label>
                  <Input
                    id="timezone"
                    value={timezone}
                    onChange={(event) => setTimezone(event.target.value)}
                    disabled={submitMutation.isPending}
                    className="mt-1"
                  />
                </div>
                <div className="rounded-lg border border-border bg-card p-3">
                  <Label htmlFor="ai-provider">Provider AI</Label>
                  <select
                    id="ai-provider"
                    value={aiProvider}
                    onChange={(event) => {
                      const next = event.target.value;
                      setAiProvider(next);
                      if (next === "auto") setAiAccountId("default");
                    }}
                    disabled={!useAi || submitMutation.isPending}
                    className="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 text-sm disabled:opacity-60"
                  >
                    {providerOptions.map((provider) => (
                      <option key={provider} value={provider}>
                        {provider}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="rounded-lg border border-border bg-card p-3">
                  <Label htmlFor="ai-account">Akun AI</Label>
                  <select
                    id="ai-account"
                    value={aiAccountId}
                    onChange={(event) => setAiAccountId(event.target.value)}
                    disabled={!useAi || aiProvider === "auto" || submitMutation.isPending}
                    className="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 text-sm disabled:opacity-60"
                  >
                    {accountOptions.map((accountId) => (
                      <option key={accountId} value={accountId}>
                        {accountId}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </details>

            <Button type="submit" disabled={submitMutation.isPending}>
              {submitMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Memproses...
                </>
              ) : (
                <>
                  <PlayCircle className="mr-2 h-4 w-4" />
                  Jalankan Sekarang
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Hasil Eksekusi</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">Planner</p>
                <p className="mt-1"><span className={plannerClass}>{plannerLabel}</span></p>
              </div>
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">Total Job</p>
                <p className="mt-1 text-xl font-semibold">{resultSummary?.total || 0}</p>
              </div>
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">Simpan</p>
                <p className="mt-1 text-sm">
                  {resultSummary?.created || 0} dibuat, {resultSummary?.updated || 0} update, {resultSummary?.errored || 0} error
                </p>
              </div>
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">Run</p>
                <p className="mt-1 text-sm">
                  {resultSummary?.runSuccess || 0} berhasil, {resultSummary?.runFailed || 0} gagal
                </p>
              </div>
            </div>

            <div className="rounded-lg border border-border bg-muted/20 p-3">
              <p className="text-sm font-medium">Ringkasan</p>
              <p className="mt-1 text-sm text-muted-foreground">{result.summary}</p>
            </div>

            {result.warnings.length > 0 ? (
              <div className="rounded-lg border border-amber-800/40 bg-amber-950/20 p-3">
                <p className="flex items-center gap-2 text-sm font-medium text-amber-300">
                  <AlertTriangle className="h-4 w-4" />
                  Catatan
                </p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-200">
                  {result.warnings.slice(0, 6).map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {result.assumptions.length > 0 ? (
              <div className="rounded-lg border border-border bg-muted/20 p-3">
                <p className="text-sm font-medium">Asumsi</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-muted-foreground">
                  {result.assumptions.slice(0, 6).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job</TableHead>
                  <TableHead>Tipe</TableHead>
                  <TableHead>Simpan</TableHead>
                  <TableHead>Run</TableHead>
                  <TableHead>Catatan</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.results.map((row) => (
                  <TableRow key={`${row.job_id}-${row.run_id || "none"}`}>
                    <TableCell className="font-medium">{row.job_id}</TableCell>
                    <TableCell>{row.type}</TableCell>
                    <TableCell>
                      <span className={getCreateStatusClass(row.create_status)}>{getCreateStatusLabel(row.create_status)}</span>
                    </TableCell>
                    <TableCell>
                      <span className={getRunStatusClass(row.run_status)}>{getRunStatusLabel(row.run_status)}</span>
                    </TableCell>
                    <TableCell className="text-xs">
                      {row.result_error ? (
                        row.result_error
                      ) : row.result_success ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400">
                          <CheckCircle2 className="h-4 w-4" />
                          Berhasil
                        </span>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Belum ada hasil. Kirim satu perintah untuk melihat ringkasannya.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
