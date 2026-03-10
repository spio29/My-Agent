export default function IncidentsPage() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Incidents</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Ruang operator untuk antrian issue, recovery proposal, approval lane, dan keputusan
          tindak lanjut.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        <article className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Queue</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">Open incidents belum dimigrasikan</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Halaman ini sengaja mulai dari shell yang tenang sebelum daftar incident baru
            dipasang.
          </p>
        </article>
        <article className="rounded-[24px] border border-slate-200 bg-white p-5 shadow-[0_10px_30px_rgba(15,23,42,0.05)]">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Recovery</p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">Approval lane siap ditambahkan</h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Recovery recommendation dan panel approval akan dipasang di task interaksi berikutnya.
          </p>
        </article>
      </section>
    </div>
  );
}
