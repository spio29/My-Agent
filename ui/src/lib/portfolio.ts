import type { Branch, InfluencerProfile } from "@/lib/api";

export type PortfolioTone = "neutral" | "info" | "success" | "warning" | "critical";

export type PortfolioBinding = {
  id: string;
  platformKey: string;
  label: string;
  handle: string;
  status: "connected" | "missing";
  note: string;
};

export type PortfolioAccount = {
  id: string;
  platform: string;
  label: string;
  handle: string;
  role: string;
  status: "ready" | "needs_review";
  note: string;
};

export type PortfolioInfluencer = {
  id: string;
  name: string;
  niche: string;
  mode: string;
  status: string;
  offerName: string;
  offerPrice: number;
  templateId: string;
  branchId: string;
  branchName: string;
  summary: string;
  tone: PortfolioTone;
  platformBindings: PortfolioBinding[];
  accounts: PortfolioAccount[];
  searchableText: string;
};

const platformLabelMap: Record<string, string> = {
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube: "YouTube",
  telegram: "Telegram",
  whatsapp: "WhatsApp",
  email: "Email",
};

const normalizePlatformLabel = (value: string): string => {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "Channel";
  return platformLabelMap[key] || key.charAt(0).toUpperCase() + key.slice(1);
};

const normalizeHandle = (value: string): string => {
  const clean = String(value || "").trim();
  if (!clean) return "Not connected";
  if (clean.startsWith("@")) return clean;
  return `@${clean}`;
};

const resolvePortfolioTone = (status: string, bindings: PortfolioBinding[]): PortfolioTone => {
  const normalizedStatus = String(status || "").trim().toLowerCase();
  if (normalizedStatus === "active" && bindings.length > 0) return "success";
  if (normalizedStatus === "paused") return "warning";
  if (normalizedStatus === "archived") return "neutral";
  if (bindings.length === 0) return "warning";
  return "info";
};

export const formatPortfolioCurrency = (value: number): string =>
  new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(Number(value || 0));

export const adaptPortfolioInfluencers = (
  profiles: InfluencerProfile[],
  branches: Branch[],
): PortfolioInfluencer[] => {
  const branchNameById = new Map(branches.map((branch) => [branch.branch_id, branch.name]));

  return profiles
    .map((profile) => {
      const channelEntries = Object.entries(profile.channels || {});
      const platformBindings: PortfolioBinding[] = channelEntries.map(([platformKey, rawHandle], index) => {
        const hasHandle = Boolean(String(rawHandle || "").trim());

        return {
          id: `${profile.influencer_id}-${platformKey}-${index}`,
          platformKey,
          label: normalizePlatformLabel(platformKey),
          handle: normalizeHandle(String(rawHandle || "")),
          status: hasHandle ? "connected" : "missing",
          note: hasHandle ? "Connected to an active publishing handle." : "This platform still needs a linked handle.",
        };
      });

      const accounts: PortfolioAccount[] = platformBindings.map((binding, index) => ({
        id: `${profile.influencer_id}-account-${binding.platformKey}-${index}`,
        platform: binding.label,
        label: index === 0 ? "Primary account" : "Connected account",
        handle: binding.handle,
        role: index === 0 ? "Primary" : "Support",
        status: index === 0 ? "ready" : "needs_review",
        note:
          index === 0
            ? "Used by default when the operator opens this portfolio."
            : "Available as additional routing or fallback coverage.",
      }));

      const branchName =
        branchNameById.get(profile.branch_id) || (profile.branch_id ? profile.branch_id : "No branch linked");
      const tone = resolvePortfolioTone(profile.status, platformBindings);
      const summary = [
        profile.niche || "Niche belum diisi",
        profile.offer_name || "Offer belum diisi",
        `${platformBindings.length} platform`,
      ]
        .filter(Boolean)
        .join(" • ");

      return {
        id: profile.influencer_id,
        name: profile.name || profile.influencer_id,
        niche: profile.niche || "Niche belum diisi",
        mode: profile.mode || "product",
        status: profile.status || "draft",
        offerName: profile.offer_name || "Offer belum diisi",
        offerPrice: Number(profile.offer_price || 0),
        templateId: profile.template_id || "No template",
        branchId: profile.branch_id || "",
        branchName,
        summary,
        tone,
        platformBindings,
        accounts,
        searchableText: [
          profile.name,
          profile.influencer_id,
          profile.niche,
          profile.offer_name,
          profile.branch_id,
          branchName,
          ...channelEntries.flatMap(([platformKey, handle]) => [platformKey, handle]),
        ]
          .join(" ")
          .toLowerCase(),
      };
    })
    .sort((left, right) => left.name.localeCompare(right.name, "id-ID"));
};

export const matchesPortfolioSearch = (portfolio: PortfolioInfluencer, search: string): boolean => {
  const normalizedSearch = String(search || "").trim().toLowerCase();
  if (!normalizedSearch) return true;
  return portfolio.searchableText.includes(normalizedSearch);
};
