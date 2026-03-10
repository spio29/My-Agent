export default function WorkflowsPage() {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <section className="rounded-[28px] border border-slate-200 bg-white/92 px-6 py-6 shadow-[0_12px_36px_rgba(15,23,42,0.05)] sm:px-8">
        <h2 className="text-3xl font-semibold tracking-[-0.03em] text-slate-950">Workflows</h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
          Halaman ini disiapkan untuk memantau blueprint objective, status lane aktif, dan kontrol
          enable atau disable workflow.
        </p>
      </section>

      <section className="rounded-[28px] border border-dashed border-slate-300 bg-[#faf9f5] px-6 py-10 shadow-[0_10px_30px_rgba(15,23,42,0.03)] sm:px-8">
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-slate-500">Empty state</p>
        <h3 className="mt-2 text-xl font-semibold tracking-[-0.02em] text-slate-950">
          Workflow inventory belum dihubungkan ke surface baru
        </h3>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600">
          Task berikutnya akan menambahkan daftar workflow, filter status, dan detail lane yang
          bisa diperiksa tanpa keluar dari konteks operator.
        </p>
      </section>
    </div>
  );
}
