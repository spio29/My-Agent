export default function InfluencersPage() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Influencers</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Halaman ini menjadi roster operator untuk binding platform, primary account, dan readiness
          tiap influencer.
        </p>
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <article className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Roster</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">Belum ada daftar netral baru</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Task berikutnya akan mengisi halaman ini dengan daftar influencer dan panel detail.
          </p>
        </article>
        <article className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Bindings</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">Platform mapping</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Siapkan status akun utama, fallback account, dan coverage per platform.
          </p>
        </article>
        <article className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Health</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">Operator checklist</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Empty state ini sengaja netral sampai data portofolio baru dihubungkan.
          </p>
        </article>
      </section>
    </div>
  );
}
