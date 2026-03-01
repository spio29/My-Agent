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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  cloneInfluencerFromTemplate,
  getBranches,
  getBoardroomHistory,
  getInfluencerProfiles,
  getInfluencerTemplates,
  getJobs,
  getJobVersions,
  rollbackJobVersion,
  getSystemInfrastructure,
  sendChairmanMandate,
  updateInfluencerProfile,
  type Branch,
  type CloneInfluencerTemplateResponse,
  type UpdateInfluencerProfileResponse,
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

const buildBriefPreview = (text: string) => {
  const normalized = sanitizeBoardroomText(text)
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\|/g, " ")
    .replace(/[*_#>]+/g, " ")
    .replace(/^\s*\d+[.)]\s*/gm, "")
    .replace(/\s+/g, " ")
    .trim();

  if (!normalized) return "Belum ada brief.";

  const sentences =
    normalized
      .match(/[^.!?]+[.!?]?/g)
      ?.map((sentence) => sentence.trim())
      .filter(Boolean) || [];

  const concise = (sentences.length ? sentences.slice(0, 2).join(" ") : normalized).trim();
  if (concise.length <= 190) return concise;
  return `${concise.slice(0, 187)}...`;
};

const splitChatParagraphs = (text: string) => {
  const normalized = sanitizeBoardroomText(text)
    .replace(/\r/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!normalized) return [];
  const paragraphs = normalized
    .split(/\n{2,}/)
    .map((part) => part.replace(/\n+/g, " ").trim())
    .filter(Boolean);
  return paragraphs.length > 0 ? paragraphs : [normalized];
};

const buildBriefPoints = (text: string) => {
  const normalized = sanitizeBoardroomText(text)
    .replace(/\r/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (!normalized) return [];

  const lines = normalized
    .split(/\n+/)
    .map((line) => line.replace(/^\s*(?:[-*]|\d+[.)])\s*/, "").trim())
    .filter(Boolean);

  const source =
    lines.length >= 2
      ? lines
      : normalized
          .match(/[^.!?]+[.!?]?/g)
          ?.map((sentence) => sentence.trim())
          .filter(Boolean) || [normalized];

  return source
    .slice(0, 4)
    .map((item) => item.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .map((item) => (item.length > 112 ? `${item.slice(0, 109)}...` : item));
};

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
  if (status === "active") return "border-[#42A5F5]/45 bg-[#42A5F5]/22 text-[#1F5D93]";
  if (status === "paused") return "border-white bg-white/80 text-blue-900/60";
  return "border-white bg-white/80 text-blue-900/60";
};

const parseInfraStatus = (status?: string) => {
  const value = String(status || "").toLowerCase();
  if (value === "ok" || value === "ready") return "online";
  if (!value) return "checking";
  return "attention";
};

const formatUpdatedAt = (value?: string) => {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "-";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
};

const resolveBranchTimestamp = (branch?: Branch | null) =>
  String(branch?.updated_at || branch?.created_at || "").trim();

const formatUpdatedLabel = (branch?: Branch | null) => {
  const formatted = formatUpdatedAt(resolveBranchTimestamp(branch));
  return formatted === "-" ? "belum tercatat" : formatted;
};

const getSquadCoverage = (branch: Branch): number => {
  const squad = branch.squad || {};
  const total = 3;
  const ready = [squad.hunter_job_id, squad.marketer_job_id, squad.closer_job_id].filter((item) => Boolean(item)).length;
  return Math.round((ready / total) * 100);
};

type PriorityLevel = "critical" | "high" | "medium" | "low";
type SignalTone = "green" | "yellow" | "red";

type BranchRow = {
  branch: Branch;
  readiness: number;
  priorityScore: number;
  priorityLevel: PriorityLevel;
  priorityNote: string;
};

const SIGNAL_STYLE: Record<
  SignalTone,
  { card: string; value: string; dot: string; text: string; bar: string }
> = {
  green: {
    card: "border-emerald-300/70 bg-emerald-50/60",
    value: "text-emerald-700",
    dot: "bg-emerald-500",
    text: "text-emerald-700",
    bar: "bg-emerald-600",
  },
  yellow: {
    card: "border-amber-300/70 bg-amber-50/55",
    value: "text-amber-700",
    dot: "bg-amber-500",
    text: "text-amber-700",
    bar: "bg-amber-600",
  },
  red: {
    card: "border-rose-300/70 bg-rose-50/55",
    value: "text-rose-700",
    dot: "bg-rose-500",
    text: "text-rose-700",
    bar: "bg-rose-600",
  },
};

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

const getPriorityLevel = (score: number): PriorityLevel => {
  if (score >= 72) return "critical";
  if (score >= 48) return "high";
  if (score >= 25) return "medium";
  return "low";
};

const getPriorityBadgeStyle = (level: PriorityLevel) => {
  if (level === "critical") return "border-rose-300 bg-rose-100 text-rose-700";
  if (level === "high") return "border-amber-300 bg-amber-100 text-amber-700";
  if (level === "medium") return "border-sky-300 bg-sky-100 text-sky-700";
  return "border-slate-300 bg-slate-100 text-slate-600";
};

const getPriorityLabel = (level: PriorityLevel) => {
  if (level === "critical") return "Critical";
  if (level === "high") return "High";
  if (level === "medium") return "Medium";
  return "Low";
};

const getBranchPriority = (branch: Branch, readiness: number) => {
  const leads = Number(branch.current_metrics?.leads || 0);
  const closings = Number(branch.current_metrics?.closings || 0);
  const closeRate = leads > 0 ? clamp(closings / leads, 0, 1) : closings > 0 ? 1 : 0;

  const readinessGap = 100 - readiness;
  const leadPressure = (Math.min(leads, 24) / 24) * 35;
  const closingGapPressure = leads > 0 ? (1 - closeRate) * 30 : 12;
  const statusAdjustment = branch.status === "active" ? 0 : -8;

  const score = clamp(readinessGap * 0.45 + leadPressure + closingGapPressure + statusAdjustment, 0, 100);
  const level = getPriorityLevel(score);

  const notes: string[] = [];
  if (readiness < 60) notes.push("ready rendah");
  if (leads >= 3 && closeRate < 0.35) notes.push("lead tinggi, close rendah");
  if (branch.status !== "active") notes.push("status non-aktif");
  if (notes.length === 0) notes.push("stabil");

  return {
    score,
    level,
    note: notes.slice(0, 2).join(" - "),
  };
};

const getRevenueTone = (totalRevenue: number, totalLeads: number): SignalTone => {
  if (totalRevenue > 0) return "green";
  if (totalLeads > 0) return "yellow";
  return "red";
};

const getUnitsTone = (activeUnits: number, totalUnits: number): SignalTone => {
  if (activeUnits === 0) return "red";
  if (activeUnits >= Math.max(1, Math.ceil(totalUnits * 0.6))) return "green";
  return "yellow";
};

const getLeadsTone = (totalLeads: number, activeUnits: number): SignalTone => {
  const healthyTarget = Math.max(3, activeUnits * 3);
  if (totalLeads >= healthyTarget) return "green";
  if (totalLeads > 0) return "yellow";
  return "red";
};

const getReadinessTone = (readinessAverage: number): SignalTone => {
  if (readinessAverage >= 80) return "green";
  if (readinessAverage >= 60) return "yellow";
  return "red";
};

const getSignalLabel = (tone: SignalTone) => {
  if (tone === "green") return "stabil";
  if (tone === "yellow") return "pantau";
  return "aksi";
};

const serializeChannelsMap = (channels: Record<string, string> | undefined): string => {
  const entries = Object.entries(channels || {}).filter(([, value]) => String(value || "").trim());
  entries.sort(([left], [right]) => left.localeCompare(right));
  return entries.map(([platform, handle]) => `${platform}=${handle}`).join("\n");
};

const parseChannelsText = (text: string): { channels: Record<string, string>; error: string } => {
  const output: Record<string, string> = {};
  const rows = String(text || "")
    .split(/\r?\n/)
    .map((row) => row.trim())
    .filter(Boolean);

  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    const separator = row.indexOf("=");
    if (separator <= 0 || separator === row.length - 1) {
      return {
        channels: {},
        error: `Format channel baris ${index + 1} tidak valid. Pakai format platform=handle.`,
      };
    }
    const platform = row.slice(0, separator).trim().toLowerCase();
    const handle = row.slice(separator + 1).trim();
    if (!platform || !handle) {
      return {
        channels: {},
        error: `Channel baris ${index + 1} wajib isi platform dan handle.`,
      };
    }
    output[platform] = handle;
  }

  return { channels: output, error: "" };
};

export default function ChairmanDashboard() {
  const queryClient = useQueryClient();
  const [activeBranchId, setActiveBranchId] = useState<string | null>(null);
  const [mandateText, setMandateText] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [cloneName, setCloneName] = useState("");
  const [cloneInfluencerId, setCloneInfluencerId] = useState("");
  const [cloneNiche, setCloneNiche] = useState("");
  const [cloneMode, setCloneMode] = useState("product");
  const [cloneBranchId, setCloneBranchId] = useState("");
  const [cloneOfferName, setCloneOfferName] = useState("");
  const [cloneOfferPrice, setCloneOfferPrice] = useState("0");
  const [cloneEnableJobs, setCloneEnableJobs] = useState(true);
  const [editorInfluencerId, setEditorInfluencerId] = useState("");
  const [editorTemplateId, setEditorTemplateId] = useState("");
  const [editorBranchId, setEditorBranchId] = useState("");
  const [editorName, setEditorName] = useState("");
  const [editorNiche, setEditorNiche] = useState("");
  const [editorMode, setEditorMode] = useState("product");
  const [editorStatus, setEditorStatus] = useState("active");
  const [editorOfferName, setEditorOfferName] = useState("");
  const [editorOfferPrice, setEditorOfferPrice] = useState("0");
  const [editorChannelsText, setEditorChannelsText] = useState("");
  const [editorChannelsError, setEditorChannelsError] = useState("");
  const [editorApplyTemplateJobs, setEditorApplyTemplateJobs] = useState(true);
  const [editorEnableJobs, setEditorEnableJobs] = useState(true);
  const [editorOverwriteJobs, setEditorOverwriteJobs] = useState(true);
  const [rollbackInfluencerId, setRollbackInfluencerId] = useState("");
  const [rollbackJobId, setRollbackJobId] = useState("");
  const [rollbackVersionId, setRollbackVersionId] = useState("");
  const [lastCloneResult, setLastCloneResult] = useState<CloneInfluencerTemplateResponse | null>(null);
  const [lastUpdateResult, setLastUpdateResult] = useState<UpdateInfluencerProfileResponse | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

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

  const { data: influencerTemplates = [] } = useQuery({
    queryKey: ["influencer-templates"],
    queryFn: () => getInfluencerTemplates(200),
    refetchInterval: 30000,
  });

  const { data: influencerProfiles = [] } = useQuery({
    queryKey: ["influencer-profiles"],
    queryFn: () => getInfluencerProfiles(200),
    refetchInterval: 12000,
  });

  const { data: influencerJobs = [] } = useQuery({
    queryKey: ["influencer-jobs", rollbackInfluencerId],
    queryFn: async () => {
      if (!rollbackInfluencerId) return [];
      return await getJobs({ search: `inf-${rollbackInfluencerId}-`, limit: 120 });
    },
    enabled: Boolean(rollbackInfluencerId),
    refetchInterval: 12000,
  });

  const { data: rollbackVersions = [] } = useQuery({
    queryKey: ["job-versions", rollbackJobId],
    queryFn: async () => {
      if (!rollbackJobId) return [];
      return await getJobVersions(rollbackJobId, 25);
    },
    enabled: Boolean(rollbackJobId),
    refetchInterval: 12000,
  });

  const mandateMutation = useMutation({
    mutationFn: sendChairmanMandate,
    onSuccess: () => {
      setMandateText("");
      queryClient.invalidateQueries({ queryKey: ["boardroom-chat"] });
    },
  });

  const cloneTemplateMutation = useMutation({
    mutationFn: async () =>
      cloneInfluencerFromTemplate(selectedTemplateId, {
        influencer_id: cloneInfluencerId.trim() || undefined,
        name: cloneName.trim(),
        niche: cloneNiche.trim(),
        mode: cloneMode,
        branch_id: cloneBranchId,
        offer_name: cloneOfferName.trim(),
        offer_price: Number(cloneOfferPrice) || 0,
        enable_jobs: cloneEnableJobs,
        overwrite_existing_jobs: true,
      }),
    onSuccess: (result) => {
      if (!result) return;
      setLastCloneResult(result);
      setRollbackInfluencerId(result.influencer.influencer_id);
      queryClient.invalidateQueries({ queryKey: ["influencer-profiles"] });
      queryClient.invalidateQueries({ queryKey: ["influencer-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const rollbackMutation = useMutation({
    mutationFn: async () => rollbackJobVersion(rollbackJobId, rollbackVersionId),
    onSuccess: (result) => {
      if (!result) return;
      queryClient.invalidateQueries({ queryKey: ["job-versions", rollbackJobId] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const updateInfluencerMutation = useMutation({
    mutationFn: async () => {
      const parsedChannels = parseChannelsText(editorChannelsText);
      if (parsedChannels.error) {
        throw new Error(parsedChannels.error);
      }
      return await updateInfluencerProfile(editorInfluencerId, {
        template_id: editorTemplateId.trim() || undefined,
        branch_id: editorBranchId.trim() || undefined,
        name: editorName.trim() || undefined,
        niche: editorNiche.trim() || undefined,
        mode: editorMode,
        status: editorStatus,
        offer_name: editorOfferName.trim() || undefined,
        offer_price: Number(editorOfferPrice) || 0,
        channels: parsedChannels.channels,
        apply_template_jobs: editorApplyTemplateJobs,
        enable_jobs: editorEnableJobs,
        overwrite_existing_jobs: editorOverwriteJobs,
      });
    },
    onSuccess: (result) => {
      if (!result) return;
      setEditorChannelsError("");
      setLastUpdateResult(result);
      setRollbackInfluencerId(result.influencer.influencer_id);
      queryClient.invalidateQueries({ queryKey: ["influencer-profiles"] });
      queryClient.invalidateQueries({ queryKey: ["influencer-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (error) => {
      setEditorChannelsError(error instanceof Error ? error.message : "Format channel tidak valid.");
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

  const branchRows = useMemo<BranchRow[]>(
    () =>
      branches
        .map((branch) => {
          const readiness = getBranchReadiness(branch);
          const priority = getBranchPriority(branch, readiness);
          return {
            branch,
            readiness,
            priorityScore: priority.score,
            priorityLevel: priority.level,
            priorityNote: priority.note,
          };
        })
        .sort((left, right) => {
          if (right.priorityScore !== left.priorityScore) return right.priorityScore - left.priorityScore;
          const leftTime = new Date(resolveBranchTimestamp(left.branch)).getTime() || 0;
          const rightTime = new Date(resolveBranchTimestamp(right.branch)).getTime() || 0;
          return rightTime - leftTime;
        }),
    [branches],
  );
  const activeBranch = useMemo(
    () => branchRows.find((row) => row.branch.branch_id === activeBranchId)?.branch || null,
    [branchRows, activeBranchId],
  );
  const activeBranchRow = useMemo(() => branchRows.find((row) => row.branch.branch_id === activeBranchId) || null, [branchRows, activeBranchId]);
  const selectedTemplate = useMemo(
    () => influencerTemplates.find((row) => row.template_id === selectedTemplateId) || null,
    [influencerTemplates, selectedTemplateId],
  );
  const selectedEditorProfile = useMemo(
    () => influencerProfiles.find((row) => row.influencer_id === editorInfluencerId) || null,
    [influencerProfiles, editorInfluencerId],
  );

  const latestCeoMessage = useMemo(() => {
    const ceoMessages = [...sanitizedChatHistory].reverse().filter((message) => message.sender === "CEO");
    return ceoMessages[0] ? buildBriefPreview(ceoMessages[0].text) : "Belum ada brief.";
  }, [sanitizedChatHistory]);
  const latestCeoEntry = useMemo(
    () => [...sanitizedChatHistory].reverse().find((message) => message.sender === "CEO") || null,
    [sanitizedChatHistory],
  );
  const latestCeoDetail = useMemo(() => {
    if (!latestCeoEntry) return "Belum ada brief.";
    return sanitizeBoardroomText(latestCeoEntry.text) || "Belum ada brief.";
  }, [latestCeoEntry]);
  const latestCeoPoints = useMemo(() => buildBriefPoints(latestCeoDetail), [latestCeoDetail]);
  const latestCeoStamp = useMemo(() => formatUpdatedAt(latestCeoEntry?.timestamp), [latestCeoEntry]);

  useEffect(() => {
    if (branchRows.length === 0) {
      if (activeBranchId !== null) setActiveBranchId(null);
      return;
    }
    const stillExists = branchRows.some((row) => row.branch.branch_id === activeBranchId);
    if (!stillExists) {
      setActiveBranchId(branchRows[0].branch.branch_id);
    }
  }, [branchRows, activeBranchId]);

  useEffect(() => {
    if (!selectedTemplateId && influencerTemplates.length > 0) {
      setSelectedTemplateId(influencerTemplates[0].template_id);
    }
  }, [influencerTemplates, selectedTemplateId]);

  useEffect(() => {
    if (!editorInfluencerId && influencerProfiles.length > 0) {
      setEditorInfluencerId(influencerProfiles[0].influencer_id);
    }
  }, [editorInfluencerId, influencerProfiles]);

  useEffect(() => {
    if (!selectedEditorProfile) return;
    setEditorTemplateId(String(selectedEditorProfile.template_id || ""));
    setEditorBranchId(String(selectedEditorProfile.branch_id || ""));
    setEditorName(String(selectedEditorProfile.name || ""));
    setEditorNiche(String(selectedEditorProfile.niche || ""));
    setEditorMode(String(selectedEditorProfile.mode || "product"));
    setEditorStatus(String(selectedEditorProfile.status || "active"));
    setEditorOfferName(String(selectedEditorProfile.offer_name || ""));
    setEditorOfferPrice(String(Number(selectedEditorProfile.offer_price || 0)));
    setEditorChannelsText(serializeChannelsMap(selectedEditorProfile.channels));
    setEditorChannelsError("");
  }, [selectedEditorProfile]);

  useEffect(() => {
    const preferredBranch = selectedTemplate?.default_branch_id || activeBranchId || branchRows[0]?.branch.branch_id || "br_01";
    if (!cloneBranchId) {
      setCloneBranchId(preferredBranch);
    }
  }, [selectedTemplate, activeBranchId, branchRows, cloneBranchId]);

  useEffect(() => {
    if (selectedTemplate?.mode) {
      setCloneMode(String(selectedTemplate.mode));
    }
  }, [selectedTemplateId, selectedTemplate?.mode]);

  useEffect(() => {
    if (!rollbackInfluencerId) return;
    const exists = influencerProfiles.some((row) => row.influencer_id === rollbackInfluencerId);
    if (!exists && influencerProfiles.length > 0) {
      setRollbackInfluencerId(influencerProfiles[0].influencer_id);
    }
  }, [rollbackInfluencerId, influencerProfiles]);

  useEffect(() => {
    if (!rollbackInfluencerId && influencerProfiles.length > 0) {
      setRollbackInfluencerId(influencerProfiles[0].influencer_id);
    }
  }, [rollbackInfluencerId, influencerProfiles]);

  useEffect(() => {
    if (influencerJobs.length === 0) {
      if (rollbackJobId) setRollbackJobId("");
      return;
    }
    const stillExists = influencerJobs.some((row) => row.job_id === rollbackJobId);
    if (!stillExists) {
      setRollbackJobId(influencerJobs[0].job_id);
    }
  }, [influencerJobs, rollbackJobId]);

  useEffect(() => {
    if (rollbackVersions.length === 0) {
      if (rollbackVersionId) setRollbackVersionId("");
      return;
    }
    const stillExists = rollbackVersions.some((row) => row.version_id === rollbackVersionId);
    if (!stillExists) {
      setRollbackVersionId(rollbackVersions[0].version_id);
    }
  }, [rollbackVersions, rollbackVersionId]);

  const syncComposerHeight = () => {
    const node = composerRef.current;
    if (!node) return;
    node.style.height = "auto";
    const maxHeight = 156;
    const nextHeight = Math.min(node.scrollHeight, maxHeight);
    node.style.height = `${nextHeight}px`;
    node.style.overflowY = node.scrollHeight > maxHeight ? "auto" : "hidden";
  };

  useEffect(() => {
    syncComposerHeight();
  }, [mandateText]);

  const submitMandate = () => {
    const cleaned = mandateText.trim();
    if (!cleaned || mandateMutation.isPending) return;
    mandateMutation.mutate(cleaned);
  };

  const handleSendMandate = (event: React.FormEvent) => {
    event.preventDefault();
    submitMandate();
  };

  const handleComposerKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      submitMandate();
    }
  };

  const submitTemplateClone = (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedTemplateId || !cloneName.trim() || cloneTemplateMutation.isPending) return;
    cloneTemplateMutation.mutate();
  };

  const submitInfluencerUpdate = (event: React.FormEvent) => {
    event.preventDefault();
    if (!editorInfluencerId || !editorName.trim() || updateInfluencerMutation.isPending) return;
    updateInfluencerMutation.mutate();
  };

  const submitRollback = (event: React.FormEvent) => {
    event.preventDefault();
    if (!rollbackJobId || !rollbackVersionId || rollbackMutation.isPending) return;
    rollbackMutation.mutate();
  };

  const healthItems = [
    { label: "API", value: infra.api?.status?.toUpperCase() || "CHECK", state: parseInfraStatus(infra.api?.status) },
    { label: "REDIS", value: infra.redis?.memory_used || "OFF", state: parseInfraStatus(infra.redis?.status) },
    {
      label: "AI",
      value: infra.ai_factory?.status?.toUpperCase() || "NONE",
      state: parseInfraStatus(infra.ai_factory?.status),
    },
  ];

  const pipelineMaturity = activeBranch
    ? Math.min(
        100,
        (activeBranch.current_metrics?.closings || 0) > 0 ? 100 : (activeBranch.current_metrics?.leads || 0) > 0 ? 60 : 25,
      )
    : 0;
  const squadCoverage = activeBranch ? getSquadCoverage(activeBranch) : 0;
  const focusPriorityLevel = activeBranchRow?.priorityLevel || "low";
  const focusPriorityStyle = getPriorityBadgeStyle(focusPriorityLevel);
  const focusPriorityLabel = getPriorityLabel(focusPriorityLevel);
  const focusPriorityNote = activeBranchRow?.priorityNote || "Belum ada catatan prioritas.";
  const focusActionHint = useMemo(() => {
    if (!activeBranch || !activeBranchRow) return "Pilih unit agar rekomendasi aksi muncul.";
    const leads = Number(activeBranch.current_metrics?.leads || 0);
    const closings = Number(activeBranch.current_metrics?.closings || 0);
    const readiness = activeBranchRow.readiness;

    if (activeBranch.status !== "active") return "Aktifkan unit ini dulu sebelum push lead baru.";
    if (leads > 0 && closings === 0) return "Prioritaskan follow-up cepat: DM/WA, reminder 24 jam, lalu jadwalkan call.";
    if (readiness < 70) return "Lengkapi readiness tim dulu agar lead masuk tidak macet di tengah pipeline.";
    if (pipelineMaturity < 80) return "Perkuat CTA di konten dan arahkan lead ke flow follow-up otomatis.";
    return "Unit sudah stabil. Fokus di optimasi conversion dan retensi.";
  }, [activeBranch, activeBranchRow, pipelineMaturity]);
  const revenueTone = getRevenueTone(totalRevenue, totalLeads);
  const unitsTone = getUnitsTone(activeUnits, branches.length);
  const leadsTone = getLeadsTone(totalLeads, activeUnits);
  const readinessTone = getReadinessTone(readinessAverage);
  const avgRevenuePerUnit = activeUnits > 0 ? Math.round(totalRevenue / activeUnits) : 0;
  const leadsPerUnit = activeUnits > 0 ? totalLeads / activeUnits : 0;

  return (
    <div className="ux-rise-in mx-auto flex h-full min-h-0 max-w-[1680px] flex-col gap-3 text-slate-900">
      <section className="no-scrollbar grid min-h-0 flex-1 gap-3 overflow-y-auto pr-1 xl:grid-cols-[minmax(0,1.42fr)_minmax(380px,0.58fr)] 2xl:grid-cols-[minmax(0,1.48fr)_minmax(400px,0.52fr)]">
        <div className="flex min-h-0 flex-col gap-3">
          <section className="glass-island shrink-0 p-4 md:p-5">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
              <div className="space-y-2">
                <p className="inline-flex items-center gap-2 rounded-2xl border border-[#42A5F5]/45 bg-[#42A5F5]/22 px-3 py-1 text-xs font-bold tracking-wide text-[#1F5D93] font-montserrat">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Live
                </p>
                <div className="flex items-start gap-3">
                  <div className="glass-island rounded-2xl p-3 text-slate-900">
                    <Building2 className="h-6 w-6" />
                  </div>
                  <div>
                    <h1 className="font-signature text-4xl leading-none text-slate-900 md:text-5xl">Holding</h1>
                    <p className="text-xs text-blue-900/60 md:text-sm font-body-copy">Kontrol inti.</p>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 xl:w-[520px] xl:justify-end">
                {healthItems.map((item) => (
                  <div key={item.label} className="inline-flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${item.state === "online" ? "bg-emerald-500" : "bg-rose-500"}`} />
                    <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-blue-900/65 font-body-copy">{item.label}</p>
                    <p className={`text-[10px] font-semibold tracking-[0.03em] font-body-copy ${item.state === "online" ? "text-emerald-700" : "text-rose-700"}`}>
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              <Card className={`metric-card-hover border ${SIGNAL_STYLE[revenueTone].card}`}>
                <CardContent className="flex h-full flex-col p-4">
                  <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-blue-900/55 font-body-copy">Revenue</p>
                  <p
                    className={`mt-1.5 metric-number tabular-nums text-[1.34rem] leading-[1.18] tracking-[0.002em] md:text-[1.46rem] ${SIGNAL_STYLE[revenueTone].value}`}
                    style={{ fontWeight: 515 }}
                  >
                    {formatCurrency(totalRevenue)}
                  </p>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    <p className="text-[9px] font-normal tracking-[0.03em] text-blue-900/60 font-body-copy">
                      Avg/Unit <span className="font-medium text-slate-900">{formatCurrency(avgRevenuePerUnit)}</span>
                    </p>
                    <p className={`inline-flex items-center gap-1 text-[9px] font-medium tracking-[0.04em] uppercase ${SIGNAL_STYLE[revenueTone].text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${SIGNAL_STYLE[revenueTone].dot}`} />
                      {getSignalLabel(revenueTone)}
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card className={`metric-card-hover border ${SIGNAL_STYLE[unitsTone].card}`}>
                <CardContent className="flex h-full flex-col p-4">
                  <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-blue-900/55 font-body-copy">Units</p>
                  <p
                    className={`mt-1.5 metric-number text-[1.38rem] leading-[1.18] tracking-[0.002em] md:text-[1.5rem] ${SIGNAL_STYLE[unitsTone].value}`}
                    style={{ fontWeight: 515 }}
                  >
                    {activeUnits}
                  </p>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    <p className="text-[9px] font-normal tracking-[0.03em] text-blue-900/60 font-body-copy">
                      Aktif <span className="font-medium text-slate-900">{activeUnits}/{branches.length}</span>
                    </p>
                    <p className={`inline-flex items-center gap-1 text-[9px] font-medium tracking-[0.04em] uppercase ${SIGNAL_STYLE[unitsTone].text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${SIGNAL_STYLE[unitsTone].dot}`} />
                      {getSignalLabel(unitsTone)}
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card className={`metric-card-hover border ${SIGNAL_STYLE[leadsTone].card}`}>
                <CardContent className="flex h-full flex-col p-4">
                  <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-blue-900/55 font-body-copy">Leads</p>
                  <p
                    className={`mt-1.5 metric-number text-[1.38rem] leading-[1.18] tracking-[0.002em] md:text-[1.5rem] ${SIGNAL_STYLE[leadsTone].value}`}
                    style={{ fontWeight: 515 }}
                  >
                    {totalLeads}
                  </p>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    <p className="text-[9px] font-normal tracking-[0.03em] text-blue-900/60 font-body-copy">
                      Per Unit <span className="font-medium text-slate-900">{leadsPerUnit.toFixed(leadsPerUnit >= 10 ? 0 : 1)}</span>
                    </p>
                    <p className={`inline-flex items-center gap-1 text-[9px] font-medium tracking-[0.04em] uppercase ${SIGNAL_STYLE[leadsTone].text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${SIGNAL_STYLE[leadsTone].dot}`} />
                      {getSignalLabel(leadsTone)}
                    </p>
                  </div>
                </CardContent>
              </Card>

              <Card className={`metric-card-hover border ${SIGNAL_STYLE[readinessTone].card}`}>
                <CardContent className="flex h-full flex-col p-4">
                  <p className="text-[9px] font-medium uppercase tracking-[0.08em] text-blue-900/55 font-body-copy">Ready</p>
                  <p
                    className={`mt-1.5 metric-number text-[1.38rem] leading-[1.18] tracking-[0.002em] md:text-[1.5rem] ${SIGNAL_STYLE[readinessTone].value}`}
                    style={{ fontWeight: 515 }}
                  >
                    {readinessAverage}%
                  </p>
                  <div className="mt-2.5 h-2 w-full rounded-full bg-white/75">
                    <div className={`h-full rounded-full transition-all ${SIGNAL_STYLE[readinessTone].bar}`} style={{ width: `${readinessAverage}%` }} />
                  </div>
                  <div className="mt-auto flex items-center justify-between gap-2 pt-2">
                    <p className="text-[9px] font-normal tracking-[0.03em] text-blue-900/60 font-body-copy">
                      Target <span className="font-medium text-slate-900">&gt;= 80%</span>
                    </p>
                    <p className={`inline-flex items-center gap-1 text-[9px] font-medium tracking-[0.04em] uppercase ${SIGNAL_STYLE[readinessTone].text}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${SIGNAL_STYLE[readinessTone].dot}`} />
                      {getSignalLabel(readinessTone)}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </section>

          <section className="flex min-h-0 shrink-0 flex-col gap-3">
            <Card className="min-h-0 min-w-0 flex flex-col">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg font-semibold text-slate-900 font-montserrat">Units</CardTitle>
                <p className="text-[11px] text-blue-900/60 font-body-copy">Urut otomatis berdasarkan prioritas eksekusi. Klik unit untuk update panel Focus.</p>
              </CardHeader>
              <CardContent className="no-scrollbar flex-1 overflow-y-auto p-4 pt-0">
                {branchRows.length === 0 ? (
                  <div className="rounded-2xl border border-white bg-white/70 p-4 text-sm text-blue-900/60 font-body-copy">
                    Belum ada data unit.
                  </div>
                ) : (
                  <Table className="min-w-[700px] xl:min-w-[760px]">
                    <TableHeader>
                      <TableRow className="hover:bg-transparent">
                        <TableHead>Unit</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Priority</TableHead>
                        <TableHead className="text-right">Lead</TableHead>
                        <TableHead className="text-right">Close</TableHead>
                        <TableHead className="text-right">Revenue</TableHead>
                        <TableHead>Ready</TableHead>
                        <TableHead>Update</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {branchRows.map(({ branch, readiness, priorityLevel, priorityNote }) => {
                        const isActive = branch.branch_id === activeBranchId;
                        return (
                          <TableRow
                            key={branch.branch_id}
                            onClick={() => setActiveBranchId(branch.branch_id)}
                            className={`cursor-pointer text-xs ${
                              isActive
                                ? "bg-[#42A5F5]/15 hover:bg-[#42A5F5]/20"
                                : priorityLevel === "critical"
                                  ? "bg-rose-50/60 hover:bg-rose-100/60"
                                  : "hover:bg-white/60"
                            }`}
                          >
                            <TableCell className="py-3">
                              <p className="font-semibold text-slate-900 font-montserrat">{branch.name}</p>
                              <p className="text-[10px] text-blue-900/60 font-body-copy">{branch.branch_id}</p>
                            </TableCell>
                            <TableCell className="py-3">
                              <span
                                className={`inline-flex rounded-xl border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] font-montserrat ${getStatusStyle(branch.status)}`}
                              >
                                {branch.status}
                              </span>
                            </TableCell>
                            <TableCell className="py-3">
                              <span
                                className={`inline-flex rounded-xl border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] font-montserrat ${getPriorityBadgeStyle(priorityLevel)}`}
                              >
                                {getPriorityLabel(priorityLevel)}
                              </span>
                              <p className="mt-1 text-[10px] text-blue-900/60 font-body-copy">{priorityNote}</p>
                            </TableCell>
                            <TableCell className="py-3 text-right">
                              <span className="metric-number text-[13px] text-slate-900">{branch.current_metrics?.leads || 0}</span>
                            </TableCell>
                            <TableCell className="py-3 text-right">
                              <span className="metric-number text-[13px] text-slate-900">{branch.current_metrics?.closings || 0}</span>
                            </TableCell>
                            <TableCell className="py-3 text-right">
                              <span className="metric-number text-[12px] text-slate-900">{formatCurrency(branch.current_metrics?.revenue || 0)}</span>
                            </TableCell>
                            <TableCell className="py-3">
                              <div className="flex items-center gap-2">
                                <div className="h-1.5 w-16 rounded-full bg-white/80">
                                  <div className="h-full rounded-full bg-slate-900" style={{ width: `${readiness}%` }} />
                                </div>
                                <span className="metric-number text-[12px] text-slate-900">{readiness}%</span>
                              </div>
                            </TableCell>
                            <TableCell className="py-3 text-[11px] text-blue-900/60 font-body-copy">
                              {formatUpdatedAt(resolveBranchTimestamp(branch))}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            <div className="grid min-h-0 min-w-0 gap-3 xl:grid-cols-[1.08fr_0.92fr]">
              {activeBranch && (
                <Card className="min-h-[220px] min-w-0">
                  <CardHeader className="pb-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900 font-montserrat">
                          <Briefcase className="h-4 w-4 text-slate-700" />
                          Focus
                        </CardTitle>
                        <p className="mt-1 text-[11px] text-blue-900/60 font-body-copy">
                          {activeBranch.name} - update {formatUpdatedLabel(activeBranch)}
                        </p>
                      </div>
                      <span
                        className={`inline-flex rounded-xl border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.1em] font-montserrat ${focusPriorityStyle}`}
                      >
                        {focusPriorityLabel}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3 p-4 pt-0">
                    <div className="rounded-xl border border-white/80 bg-white/78 px-3 py-2">
                      <p className="text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Prioritas</p>
                      <p className="mt-1 text-[12px] leading-[1.45] text-slate-900 font-body-copy">{focusPriorityNote}</p>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="rounded-2xl bg-white/75 p-3">
                        <Target className="mx-auto mb-1 h-3.5 w-3.5 text-slate-700" />
                        <p className="text-[9px] text-blue-900/65 font-body-copy font-medium tracking-[0.04em]">Lead</p>
                        <p className="metric-number text-[1.08rem] text-slate-900">{activeBranch.current_metrics?.leads || 0}</p>
                      </div>
                      <div className="rounded-2xl bg-white/75 p-3">
                        <CheckCircle2 className="mx-auto mb-1 h-3.5 w-3.5 text-slate-700" />
                        <p className="text-[9px] text-blue-900/65 font-body-copy font-medium tracking-[0.04em]">Close</p>
                        <p className="metric-number text-[1.08rem] text-slate-900">{activeBranch.current_metrics?.closings || 0}</p>
                      </div>
                      <div className="rounded-2xl bg-white/75 p-3">
                        <TrendingUp className="mx-auto mb-1 h-3.5 w-3.5 text-slate-700" />
                        <p className="text-[9px] text-blue-900/65 font-body-copy font-medium tracking-[0.04em]">Rev</p>
                        <p className="metric-number text-[1.06rem] text-slate-900">{formatCurrency(activeBranch.current_metrics?.revenue || 0)}</p>
                      </div>
                    </div>

                    <div className="grid gap-2 md:grid-cols-2">
                      <div className="rounded-2xl bg-white/75 p-3">
                        <p className="text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Blueprint</p>
                        <p className="mt-1 truncate text-[12px] font-medium text-slate-900 font-body-copy">{activeBranch.blueprint_id || "-"}</p>
                      </div>
                      <div className="rounded-2xl bg-white/75 p-3">
                        <p className="text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Readiness</p>
                        <p className="mt-1 metric-number text-[0.96rem] text-slate-900">{activeBranchRow?.readiness ?? 0}%</p>
                      </div>
                    </div>

                    <div className="rounded-xl border border-white/80 bg-white/72 px-3 py-2.5">
                      <p className="mb-1 text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Action Hint</p>
                      <p className="text-[11px] leading-[1.5] text-slate-900 font-body-copy">{focusActionHint}</p>
                    </div>

                    <div>
                      <div className="mb-1.5 flex items-center justify-between text-[10px] font-medium tracking-[0.04em] text-blue-900/65 font-body-copy">
                        <span>Flow</span>
                        <span>{pipelineMaturity}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-white/70">
                        <div className="h-full rounded-full bg-slate-900" style={{ width: `${pipelineMaturity}%` }} />
                      </div>
                    </div>

                    <div>
                      <div className="mb-1.5 flex items-center justify-between text-[10px] font-medium tracking-[0.04em] text-blue-900/65 font-body-copy">
                        <span>Squad Coverage</span>
                        <span>{squadCoverage}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-white/70">
                        <div className="h-full rounded-full bg-[#42A5F5]" style={{ width: `${squadCoverage}%` }} />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

                <Card className="min-h-[220px] min-w-0">
                  <CardHeader className="pb-3">
                    <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900 font-montserrat">
                      <MessageSquareQuote className="h-4 w-4 text-slate-700" />
                      Brief
                    </CardTitle>
                    <p className="text-[11px] text-blue-900/60 font-body-copy">
                      Ringkasan CEO terbaru {latestCeoStamp !== "-" ? `- ${latestCeoStamp}` : ""}
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-2.5 p-4 pt-0">
                    <div className="rounded-xl border border-white/80 bg-white/72 px-3 py-2.5">
                      <p className="text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Ringkas</p>
                      <p className="mt-1 break-words text-[12px] leading-[1.55] text-slate-900 font-body-copy">{latestCeoMessage}</p>
                    </div>

                    <div className="rounded-xl border border-white/75 bg-white/65 px-3 py-2.5">
                      <p className="text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Poin aksi</p>
                      {latestCeoPoints.length === 0 ? (
                        <p className="mt-1 text-[11px] text-blue-900/60 font-body-copy">Belum ada poin aksi.</p>
                      ) : (
                        <div className="mt-1 space-y-1.5">
                          {latestCeoPoints.map((point, index) => (
                            <div key={`brief-point-${index}`} className="flex items-start gap-2">
                              <span className="mt-[6px] h-1.5 w-1.5 rounded-full bg-[#42A5F5]/80" />
                              <p className="text-[11px] leading-[1.5] text-slate-800 font-body-copy">{point}</p>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="no-scrollbar max-h-[122px] overflow-y-auto rounded-xl border border-white/75 bg-white/60 px-3 py-2.5">
                      <p className="text-[9px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Detail</p>
                      <p className="mt-1 break-words text-[11px] leading-[1.55] text-slate-700 font-body-copy">{latestCeoDetail}</p>
                    </div>
                  </CardContent>
                </Card>
              </div>

            <div className="flex min-h-0 min-w-0 flex-col gap-3">
              <div className="grid min-h-0 min-w-0 gap-3 xl:grid-cols-2">
              <Card className="min-h-[250px] min-w-0">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900 font-montserrat">
                    <Building2 className="h-4 w-4 text-slate-700" />
                    Clone Template
                  </CardTitle>
                  <p className="text-[11px] text-blue-900/60 font-body-copy">Buat influencer baru tanpa ubah struktur sistem inti.</p>
                </CardHeader>
                <CardContent className="p-4 pt-0">
                  <form onSubmit={submitTemplateClone} className="space-y-3">
                    <div className="grid gap-2 md:grid-cols-2">
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Template</p>
                        <select
                          value={selectedTemplateId}
                          onChange={(event) => setSelectedTemplateId(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="">Pilih template</option>
                          {influencerTemplates.map((template) => (
                            <option key={template.template_id} value={template.template_id}>
                              {template.name} ({template.mode})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Branch</p>
                        <select
                          value={cloneBranchId}
                          onChange={(event) => setCloneBranchId(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="">Pilih branch</option>
                          {branchRows.map(({ branch }) => (
                            <option key={branch.branch_id} value={branch.branch_id}>
                              {branch.name} ({branch.branch_id})
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="grid gap-2 md:grid-cols-3">
                      <label className="space-y-1 md:col-span-2">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Nama Influencer</p>
                        <input
                          value={cloneName}
                          onChange={(event) => setCloneName(event.target.value)}
                          placeholder="Contoh: Aira Studio"
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none placeholder:text-blue-900/45"
                        />
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">ID (opsional)</p>
                        <input
                          value={cloneInfluencerId}
                          onChange={(event) => setCloneInfluencerId(event.target.value)}
                          placeholder="auto-generate"
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none placeholder:text-blue-900/45"
                        />
                      </label>
                    </div>

                    <div className="grid gap-2 md:grid-cols-4">
                      <label className="space-y-1 md:col-span-2">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Niche</p>
                        <input
                          value={cloneNiche}
                          onChange={(event) => setCloneNiche(event.target.value)}
                          placeholder="beauty, finance, webapp, dll"
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none placeholder:text-blue-900/45"
                        />
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Mode</p>
                        <select
                          value={cloneMode}
                          onChange={(event) => setCloneMode(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="product">product</option>
                          <option value="endorse">endorse</option>
                          <option value="hybrid">hybrid</option>
                        </select>
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Harga Offer</p>
                        <input
                          value={cloneOfferPrice}
                          onChange={(event) => setCloneOfferPrice(event.target.value)}
                          type="number"
                          min={0}
                          step={1000}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        />
                      </label>
                    </div>

                    <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Offer Name</p>
                        <input
                          value={cloneOfferName}
                          onChange={(event) => setCloneOfferName(event.target.value)}
                          placeholder="contoh: Paket Landing Page Premium"
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none placeholder:text-blue-900/45"
                        />
                      </label>
                      <label className="mt-6 inline-flex items-center gap-2 text-[11px] text-blue-900/75 font-body-copy">
                        <input
                          type="checkbox"
                          checked={cloneEnableJobs}
                          onChange={(event) => setCloneEnableJobs(event.target.checked)}
                          className="h-4 w-4 rounded border-[#BFDBFE]"
                        />
                        Enable jobs
                      </label>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[10px] text-blue-900/60 font-body-copy">
                        {selectedTemplate?.description || "Pilih template untuk lihat strategi default."}
                      </p>
                      <Button
                        type="submit"
                        disabled={!selectedTemplateId || !cloneName.trim() || cloneTemplateMutation.isPending}
                        className="h-8 rounded-xl px-3 text-[11px] font-medium"
                      >
                        {cloneTemplateMutation.isPending ? "Cloning..." : "Clone Sekarang"}
                      </Button>
                    </div>
                  </form>

                  {lastCloneResult && (
                    <div className="mt-3 rounded-2xl border border-[#DBEAFE] bg-white/80 p-3">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Clone terakhir</p>
                      <p className="mt-1 text-[12px] text-slate-900 font-body-copy">
                        {lastCloneResult.influencer.name} ({lastCloneResult.influencer.influencer_id}) - {lastCloneResult.jobs.length} job
                      </p>
                      <div className="mt-2 max-h-24 space-y-1 overflow-y-auto pr-1">
                        {lastCloneResult.jobs.map((job) => (
                          <div key={job.job_id} className="flex items-center justify-between rounded-lg border border-white/80 bg-white/85 px-2 py-1.5">
                            <p className="truncate text-[11px] text-slate-900 font-body-copy">{job.job_id}</p>
                            <span className="text-[10px] uppercase tracking-[0.06em] text-blue-900/60 font-body-copy">{job.status}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="min-h-[250px] min-w-0">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900 font-montserrat">
                    <ShieldCheck className="h-4 w-4 text-slate-700" />
                    Operator No-Code
                  </CardTitle>
                  <p className="text-[11px] text-blue-900/60 font-body-copy">Update strategi influencer dari dashboard tanpa edit backend.</p>
                </CardHeader>
                <CardContent className="space-y-3 p-4 pt-0">
                  <form onSubmit={submitInfluencerUpdate} className="space-y-2.5 rounded-xl border border-[#DBEAFE] bg-white/70 p-3">
                    <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Profil & Strategi</p>

                    <label className="space-y-1">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Influencer</p>
                      <select
                        value={editorInfluencerId}
                        onChange={(event) => setEditorInfluencerId(event.target.value)}
                        className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                      >
                        <option value="">Pilih influencer</option>
                        {influencerProfiles.map((profile) => (
                          <option key={profile.influencer_id} value={profile.influencer_id}>
                            {profile.name} ({profile.influencer_id})
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="grid gap-2 md:grid-cols-2">
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Template</p>
                        <select
                          value={editorTemplateId}
                          onChange={(event) => setEditorTemplateId(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="">Pilih template</option>
                          {influencerTemplates.map((template) => (
                            <option key={template.template_id} value={template.template_id}>
                              {template.name} ({template.mode})
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Branch</p>
                        <select
                          value={editorBranchId}
                          onChange={(event) => setEditorBranchId(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="">Pilih branch</option>
                          {branchRows.map(({ branch }) => (
                            <option key={branch.branch_id} value={branch.branch_id}>
                              {branch.name} ({branch.branch_id})
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>

                    <div className="grid gap-2 md:grid-cols-2">
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Nama</p>
                        <input
                          value={editorName}
                          onChange={(event) => setEditorName(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        />
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Niche</p>
                        <input
                          value={editorNiche}
                          onChange={(event) => setEditorNiche(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        />
                      </label>
                    </div>

                    <div className="grid gap-2 md:grid-cols-4">
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Mode</p>
                        <select
                          value={editorMode}
                          onChange={(event) => setEditorMode(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="product">product</option>
                          <option value="endorse">endorse</option>
                          <option value="hybrid">hybrid</option>
                        </select>
                      </label>
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Status</p>
                        <select
                          value={editorStatus}
                          onChange={(event) => setEditorStatus(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        >
                          <option value="active">active</option>
                          <option value="paused">paused</option>
                          <option value="archived">archived</option>
                        </select>
                      </label>
                      <label className="space-y-1 md:col-span-2">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Offer</p>
                        <input
                          value={editorOfferName}
                          onChange={(event) => setEditorOfferName(event.target.value)}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        />
                      </label>
                    </div>

                    <div className="grid gap-2 md:grid-cols-[1fr_auto_auto_auto] md:items-center">
                      <label className="space-y-1">
                        <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Harga</p>
                        <input
                          value={editorOfferPrice}
                          onChange={(event) => setEditorOfferPrice(event.target.value)}
                          type="number"
                          min={0}
                          step={1000}
                          className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                        />
                      </label>
                      <label className="mt-6 inline-flex items-center gap-2 text-[11px] text-blue-900/75 font-body-copy">
                        <input
                          type="checkbox"
                          checked={editorApplyTemplateJobs}
                          onChange={(event) => setEditorApplyTemplateJobs(event.target.checked)}
                          className="h-4 w-4 rounded border-[#BFDBFE]"
                        />
                        Sinkron job
                      </label>
                      <label className="mt-6 inline-flex items-center gap-2 text-[11px] text-blue-900/75 font-body-copy">
                        <input
                          type="checkbox"
                          checked={editorEnableJobs}
                          onChange={(event) => setEditorEnableJobs(event.target.checked)}
                          className="h-4 w-4 rounded border-[#BFDBFE]"
                        />
                        Enable job
                      </label>
                      <label className="mt-6 inline-flex items-center gap-2 text-[11px] text-blue-900/75 font-body-copy">
                        <input
                          type="checkbox"
                          checked={editorOverwriteJobs}
                          onChange={(event) => setEditorOverwriteJobs(event.target.checked)}
                          className="h-4 w-4 rounded border-[#BFDBFE]"
                        />
                        Overwrite
                      </label>
                    </div>

                    <label className="space-y-1">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Channel Mapping</p>
                      <textarea
                        value={editorChannelsText}
                        onChange={(event) => {
                          setEditorChannelsText(event.target.value);
                          if (editorChannelsError) setEditorChannelsError("");
                        }}
                        rows={4}
                        placeholder={"instagram=@brand.one\nthreads=@brand.one\nx=@brandone"}
                        className="w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 py-2 text-[12px] leading-5 text-slate-900 outline-none placeholder:text-blue-900/45"
                      />
                      <p className="text-[10px] text-blue-900/60 font-body-copy">1 baris 1 channel: `platform=handle`.</p>
                      {editorChannelsError && <p className="text-[10px] text-rose-600 font-body-copy">{editorChannelsError}</p>}
                    </label>

                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[10px] text-blue-900/60 font-body-copy">Simpan update profil, channel, dan job behavior.</p>
                      <Button
                        type="submit"
                        disabled={!editorInfluencerId || !editorName.trim() || updateInfluencerMutation.isPending}
                        className="h-8 rounded-xl px-3 text-[11px] font-medium"
                      >
                        {updateInfluencerMutation.isPending ? "Menyimpan..." : "Simpan Strategi"}
                      </Button>
                    </div>
                  </form>

                  {lastUpdateResult && (
                    <div className="rounded-xl border border-[#DBEAFE] bg-white/75 p-3">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Update terakhir</p>
                      <p className="mt-1 text-[12px] text-slate-900 font-body-copy">
                        {lastUpdateResult.influencer.name} ({lastUpdateResult.influencer.influencer_id}) - {lastUpdateResult.jobs.length} job tersinkron
                      </p>
                      {lastUpdateResult.jobs.length > 0 && (
                        <div className="mt-2 max-h-24 space-y-1 overflow-y-auto pr-1">
                          {lastUpdateResult.jobs.slice(0, 6).map((job) => (
                            <div key={job.job_id} className="flex items-center justify-between rounded-lg border border-white/80 bg-white/85 px-2 py-1.5">
                              <p className="truncate text-[11px] text-slate-900 font-body-copy">{job.job_id}</p>
                              <span className="text-[10px] uppercase tracking-[0.06em] text-blue-900/60 font-body-copy">{job.status}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                </CardContent>
              </Card>

              </div>

              <Card className="min-h-[220px] min-w-0">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-900 font-montserrat">
                    <ShieldCheck className="h-4 w-4 text-slate-700" />
                    Rollback Job
                  </CardTitle>
                  <p className="text-[11px] text-blue-900/60 font-body-copy">Pulihkan konfigurasi job ke versi sebelumnya saat eksperimen tidak cocok.</p>
                </CardHeader>
                <CardContent className="space-y-3 p-4 pt-0">
                  <form onSubmit={submitRollback} className="grid gap-2.5 md:grid-cols-3">
                    <label className="space-y-1">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Influencer</p>
                      <select
                        value={rollbackInfluencerId}
                        onChange={(event) => setRollbackInfluencerId(event.target.value)}
                        className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                      >
                        <option value="">Pilih influencer</option>
                        {influencerProfiles.map((profile) => (
                          <option key={profile.influencer_id} value={profile.influencer_id}>
                            {profile.name} ({profile.influencer_id})
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="space-y-1">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Job</p>
                      <select
                        value={rollbackJobId}
                        onChange={(event) => setRollbackJobId(event.target.value)}
                        className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                      >
                        <option value="">Pilih job</option>
                        {influencerJobs.map((job) => (
                          <option key={job.job_id} value={job.job_id}>
                            {job.job_id}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="space-y-1">
                      <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Versi</p>
                      <select
                        value={rollbackVersionId}
                        onChange={(event) => setRollbackVersionId(event.target.value)}
                        className="h-9 w-full rounded-xl border border-[#BFDBFE] bg-white/85 px-3 text-[12px] text-slate-900 outline-none"
                      >
                        <option value="">Pilih versi</option>
                        {rollbackVersions.map((version) => (
                          <option key={version.version_id} value={version.version_id}>
                            {formatUpdatedAt(version.created_at)} - {version.source || "manual"}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="flex items-center justify-between gap-2 md:col-span-3">
                      <p className="text-[10px] text-blue-900/60 font-body-copy">
                        Versi tersedia: {rollbackVersions.length}
                      </p>
                      <Button
                        type="submit"
                        disabled={!rollbackJobId || !rollbackVersionId || rollbackMutation.isPending}
                        className="h-8 rounded-xl px-3 text-[11px] font-medium"
                      >
                        {rollbackMutation.isPending ? "Rollback..." : "Rollback"}
                      </Button>
                    </div>
                  </form>

                  <div className="rounded-xl border border-[#DBEAFE] bg-white/75 p-3 md:max-w-[520px]">
                    <p className="text-[10px] uppercase tracking-[0.08em] text-blue-900/60 font-body-copy">Status</p>
                    <p className="mt-1 text-[12px] text-slate-900 font-body-copy">
                      {rollbackMutation.isSuccess
                        ? "Rollback sukses. Konfigurasi job sudah dipulihkan."
                        : "Rollback siap dipakai untuk job influencer terpilih (butuh role admin)."}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </section>
        </div>

        <Card className="flex h-full min-h-0 min-w-0 flex-col">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-lg font-semibold text-slate-900 font-montserrat">
              <Bot className="h-5 w-5 text-slate-700" />
              Boardroom
            </CardTitle>
            <p className="text-[11px] text-blue-900/60 font-body-copy">Live chat.</p>
          </CardHeader>

          <CardContent className="no-scrollbar flex-1 space-y-3 overflow-y-auto p-4 pt-0">
            {sanitizedChatHistory.length === 0 && (
              <div className="rounded-2xl border border-white bg-white/70 p-4 text-sm text-blue-900/60 font-body-copy">Belum ada chat.</div>
            )}
            {sanitizedChatHistory.map((msg) => (
              <div key={msg.id} className={`flex ${msg.sender === "Chairman" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[92%] rounded-2xl border p-3 ${
                    msg.sender === "Chairman"
                      ? "border-r-[3px] border-r-[#42A5F5]/55 border-[#42A5F5]/40 bg-[#42A5F5]/16 text-[#1F5D93]"
                      : "border-l-[3px] border-l-[#60A5FA]/60 border-[#DBEAFE] bg-[#FCFDFF] text-slate-900"
                  }`}
                >
                  <p className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-blue-900/60 font-montserrat">
                    {msg.sender === "Chairman" ? <User className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
                    {msg.sender}
                  </p>
                  <div
                    className={`mb-2 h-px ${
                      msg.sender === "Chairman"
                        ? "bg-[#42A5F5]/30"
                        : "bg-gradient-to-r from-[#60A5FA]/55 via-[#BFDBFE]/35 to-transparent"
                    }`}
                  />
                  <div className="space-y-1.5">
                    {splitChatParagraphs(msg.text).map((paragraph, index) => (
                      <p key={`${msg.id}-${index}`} className="break-words text-[12px] leading-[1.65] text-slate-800 font-body-copy">
                        {paragraph}
                      </p>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </CardContent>

          <div className="border-t border-white/90 p-3">
            <form onSubmit={handleSendMandate} className="space-y-2">
              <div className="rounded-2xl border border-[#42A5F5]/30 bg-[#42A5F5]/12 p-2">
                <textarea
                  ref={composerRef}
                  rows={1}
                  placeholder="Ketik mandat..."
                  value={mandateText}
                  onChange={(e) => setMandateText(e.target.value)}
                  onKeyDown={handleComposerKeyDown}
                  className="no-scrollbar min-h-[34px] max-h-[156px] w-full resize-none bg-transparent px-1 py-1.5 text-[13px] leading-[1.55] text-slate-900 outline-none placeholder:text-blue-900/50"
                />
                <div className="mt-2 flex items-center justify-between gap-2">
                  <p className="text-[10px] tracking-[0.02em] text-blue-900/60 font-body-copy">
                    Ctrl+Enter kirim - {mandateText.length} karakter
                  </p>
                  <Button
                    type="submit"
                    disabled={mandateMutation.isPending || !mandateText.trim()}
                    className="h-8 rounded-xl px-3 text-[11px] font-medium"
                  >
                    <Send className="mr-1 h-3.5 w-3.5" />
                    Kirim
                  </Button>
                </div>
              </div>
            </form>
          </div>
        </Card>
      </section>

      <footer className="glass-island shrink-0 flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-[11px] font-semibold tracking-wide text-blue-900/60 font-montserrat">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <span className="inline-flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-slate-700" />
            3s
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-slate-700" />
            5s
          </span>
        </div>
        <div>SPIO</div>
      </footer>
    </div>
  );
}


