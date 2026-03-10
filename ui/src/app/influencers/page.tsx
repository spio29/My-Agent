"use client";

import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, UsersRound } from "lucide-react";

import SectionShell from "@/components/operator/section-shell";
import StatusPill from "@/components/operator/status-pill";
import { getBranches, getInfluencerProfiles } from "@/lib/api";
import {
  adaptPortfolioInfluencers,
  formatPortfolioCurrency,
  matchesPortfolioSearch,
} from "@/lib/portfolio";

export default function InfluencersPage() {
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const deferredSearch = useDeferredValue(search);

  const profilesQuery = useQuery({
    queryKey: ["portfolio", "profiles"],
    queryFn: () => getInfluencerProfiles({ limit: 200 }),
  });

  const branchesQuery = useQuery({
    queryKey: ["portfolio", "branches"],
    queryFn: () => getBranches(),
  });

  const portfolio = adaptPortfolioInfluencers(
    profilesQuery.data || [],
    branchesQuery.data || [],
  );

  const filteredPortfolio = portfolio.filter((item) =>
    matchesPortfolioSearch(item, deferredSearch),
  );

  useEffect(() => {
    if (filteredPortfolio.length === 0) {
      if (selectedId) {
        startTransition(() => setSelectedId(""));
      }
      return;
    }

    const selectedStillVisible = filteredPortfolio.some((item) => item.id === selectedId);
    if (!selectedId || !selectedStillVisible) {
      startTransition(() => setSelectedId(filteredPortfolio[0].id));
    }
  }, [filteredPortfolio, selectedId]);

  const selectedPortfolio =
    filteredPortfolio.find((item) => item.id === selectedId) || null;
  const isLoading = profilesQuery.isLoading || branchesQuery.isLoading;
  const hasData = filteredPortfolio.length > 0;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
      <div className="max-w-3xl">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Influencers</h2>
        <p className="mt-2 text-sm leading-6 text-slate-600">
          Workspace operator untuk membaca roster portofolio, memilih influencer aktif, dan
          memeriksa platform binding serta akun yang tersedia tanpa berpindah ke surface lama.
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.1fr)]">
        <SectionShell
          title="Portfolio"
          description="Cari dan pilih influencer yang ingin diperiksa."
          actions={
            <span className="inline-flex items-center gap-2 text-sm text-slate-500">
              <UsersRound className="h-4 w-4" />
              {filteredPortfolio.length} visible
            </span>
          }
        >
          <label className="relative block">
            <span className="sr-only">Search influencers</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              placeholder="Search influencers"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm text-slate-900 outline-none transition-colors placeholder:text-slate-400 focus:border-slate-400"
            />
          </label>

          <div className="mt-4 divide-y divide-slate-200">
            {isLoading ? (
              <div className="py-8 text-sm text-slate-500">Loading influencer roster…</div>
            ) : null}

            {!isLoading && !hasData ? (
              <div className="py-8 text-sm leading-6 text-slate-500">
                Belum ada profile influencer yang bisa ditampilkan. Tambahkan profile baru atau
                periksa kembali akses API untuk portofolio.
              </div>
            ) : null}

            {!isLoading
              ? filteredPortfolio.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => startTransition(() => setSelectedId(item.id))}
                    className={`flex w-full flex-col gap-2 px-0 py-4 text-left ${
                      item.id === selectedId ? "bg-stone-50/70" : ""
                    }`}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-slate-950">{item.name}</span>
                      <StatusPill tone={item.tone}>{item.status}</StatusPill>
                    </div>
                    <p className="text-sm text-slate-600">{item.summary}</p>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-500">
                      <span>{item.branchName}</span>
                      <span>{item.platformBindings.length} bindings</span>
                    </div>
                  </button>
                ))
              : null}
          </div>
        </SectionShell>

        <div className="flex flex-col gap-5">
          <SectionShell
            title={selectedPortfolio ? selectedPortfolio.name : "Select an influencer"}
            description={
              selectedPortfolio
                ? "Ringkasan portofolio yang sedang dipilih."
                : "Pilih satu influencer dari daftar untuk membuka detail portofolio."
            }
          >
            {selectedPortfolio ? (
              <div className="grid gap-3 md:grid-cols-2">
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Branch</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">{selectedPortfolio.branchName}</p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Mode</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">{selectedPortfolio.mode}</p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Offer</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">{selectedPortfolio.offerName}</p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Offer value</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">
                    {formatPortfolioCurrency(selectedPortfolio.offerPrice)}
                  </p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Niche</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">{selectedPortfolio.niche}</p>
                </article>
                <article className="rounded-lg border border-slate-200 bg-stone-50 px-4 py-3">
                  <p className="text-sm text-slate-500">Template</p>
                  <p className="mt-1 text-sm font-medium text-slate-900">{selectedPortfolio.templateId}</p>
                </article>
              </div>
            ) : (
              <p className="text-sm leading-6 text-slate-500">
                Detail portofolio akan muncul di sini setelah satu influencer dipilih.
              </p>
            )}
          </SectionShell>

          <SectionShell
            title="Platform bindings"
            description="Handle aktif per platform untuk influencer yang dipilih."
          >
            {selectedPortfolio && selectedPortfolio.platformBindings.length > 0 ? (
              <div className="divide-y divide-slate-200">
                {selectedPortfolio.platformBindings.map((binding) => (
                  <article
                    key={binding.id}
                    className="grid gap-3 py-3 md:grid-cols-[minmax(0,1fr)_auto]"
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-semibold text-slate-950">{binding.label}</h4>
                        <StatusPill tone={binding.status === "connected" ? "success" : "warning"}>
                          {binding.status}
                        </StatusPill>
                      </div>
                      <p className="mt-1 text-sm text-slate-600">{binding.note}</p>
                    </div>
                    <div className="text-sm text-slate-700">{binding.handle}</div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-slate-500">
                Belum ada binding platform untuk influencer ini.
              </p>
            )}
          </SectionShell>

          <SectionShell
            title="Accounts"
            description="Akun yang tersedia untuk jalur utama dan fallback."
          >
            {selectedPortfolio && selectedPortfolio.accounts.length > 0 ? (
              <div className="divide-y divide-slate-200">
                {selectedPortfolio.accounts.map((account) => (
                  <article
                    key={account.id}
                    className="grid gap-3 py-3 md:grid-cols-[minmax(0,1fr)_auto]"
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-semibold text-slate-950">{account.platform}</h4>
                        <StatusPill tone={account.status === "ready" ? "success" : "info"}>
                          {account.role}
                        </StatusPill>
                      </div>
                      <p className="mt-1 text-sm text-slate-600">{account.note}</p>
                    </div>
                    <div className="flex flex-col items-start gap-1 md:items-end">
                      <span className="text-sm font-medium text-slate-900">{account.handle}</span>
                      <span className="text-sm text-slate-500">{account.label}</span>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-6 text-slate-500">
                Akun utama dan fallback belum tersedia untuk influencer ini.
              </p>
            )}
          </SectionShell>
        </div>
      </div>
    </div>
  );
}
