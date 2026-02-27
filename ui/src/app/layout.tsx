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
      <body className={`${bodyFont.variable} antialiased`}>
        <Providers>
          <div className="min-h-screen">
            <div className="mx-auto flex min-h-screen max-w-[1600px]">
              <aside className="hidden w-72 shrink-0 border-r border-border/90 bg-card lg:flex lg:flex-col">
                <div className="border-b border-border/80 px-6 py-6">
                  <span className="inline-flex rounded-full bg-secondary px-3 py-1 text-xs font-semibold text-secondary-foreground">
                    Dasbor Operasional
                  </span>
                  <h1 className="mt-4 text-xl font-bold text-foreground">Asisten Spio</h1>
                  <p className="mt-2 text-sm text-muted-foreground">
                    Cek status sistem, jalankan tugas, dan lihat hasilnya langsung dari satu tempat.
                  </p>
                </div>

                <SidebarNav />

                <div className="mt-auto border-t border-border/80 px-6 py-4 text-xs text-muted-foreground">
                  Versi 0.1.0
                </div>
              </aside>

              <main className="scroll-stable flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
                <div className="mb-6 rounded-2xl border border-border/80 bg-card p-4 lg:hidden">
                  <h1 className="text-lg font-bold text-foreground">Asisten Spio</h1>
                  <p className="mt-1 text-sm text-muted-foreground">Pantau sistem dan jalankan tugas dengan cepat</p>
                  <SidebarNav compact />
                </div>
                {children}
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}