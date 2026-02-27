import './globals.css';
import { Plus_Jakarta_Sans } from 'next/font/google';
import SidebarNav from '@/components/sidebar-nav';

import Providers from './providers';

const bodyFont = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600', '700', '800'],
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body className={`${bodyFont.variable} h-screen w-screen overflow-hidden antialiased`}>
        <Providers>
          <div className="h-screen w-screen overflow-hidden bg-gradient-to-br from-[#EAF4FF] via-[#F0F7FF] to-[#E2EFFF] p-3 lg:p-4">
            <div className="mx-auto flex h-full max-w-[1700px] gap-3">
              <aside className="hidden h-full w-72 shrink-0 rounded-3xl border border-white bg-white/70 shadow-xl shadow-blue-900/5 backdrop-blur-xl lg:flex lg:flex-col">
                <div className="border-b border-white/80 px-6 py-6">
                  <span className="inline-flex rounded-full bg-sky-100 px-3 py-1 text-xs font-bold tracking-tight text-sky-700">
                    Dasbor Operasional
                  </span>
                  <h1 className="mt-4 text-xl font-black tracking-tighter text-slate-900">Asisten Spio</h1>
                  <p className="mt-2 text-xs text-blue-900/60">
                    Cek status sistem, jalankan tugas, dan lihat hasilnya langsung dari satu tempat.
                  </p>
                </div>

                <SidebarNav />

                <div className="mt-auto border-t border-white/80 px-6 py-4 text-xs font-semibold text-blue-900/60">Versi 0.1.0</div>
              </aside>

              <main className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
                <div className="glass-island mb-3 p-4 lg:hidden">
                  <h1 className="text-lg font-black tracking-tighter text-slate-900">Asisten Spio</h1>
                  <p className="mt-1 text-xs text-blue-900/60">Pantau sistem dan jalankan tugas dengan cepat</p>
                  <SidebarNav compact />
                </div>
                <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}