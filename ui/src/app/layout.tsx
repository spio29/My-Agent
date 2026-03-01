import './globals.css';
import { Caveat, Plus_Jakarta_Sans, Sora } from 'next/font/google';
import SidebarNav from '@/components/sidebar-nav';

import Providers from './providers';

const bodyFont = Plus_Jakarta_Sans({
  subsets: ['latin'],
  variable: '--font-body',
  weight: ['400', '500', '600', '700'],
});

const headingFont = Sora({
  subsets: ['latin'],
  variable: '--font-heading',
  weight: ['500', '600', '700'],
});

const signatureFont = Caveat({
  subsets: ['latin'],
  variable: '--font-signature',
  weight: ['600', '700'],
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="id">
      <body className={`${bodyFont.variable} ${headingFont.variable} ${signatureFont.variable} h-screen w-screen overflow-hidden antialiased`}>
        <Providers>
          <div className="relative h-screen w-screen overflow-hidden bg-gradient-to-br from-[#EAF4FF] via-[#F0F7FF] to-[#E2EFFF] p-3 lg:p-4">
            <div className="pointer-events-none absolute inset-0 overflow-hidden">
              <div className="absolute -left-24 -top-20 h-80 w-[32rem] rounded-[42%_58%_63%_37%/44%_41%_59%_56%] bg-[#B9DBFF]/55 blur-3xl" />
              <div className="absolute right-[-6rem] top-[6%] h-72 w-[28rem] rounded-[56%_44%_40%_60%/53%_45%_55%_47%] bg-[#BFF5E6]/60 blur-3xl" />
              <div className="absolute left-[30%] top-[58%] h-72 w-[34rem] rounded-[45%_55%_64%_36%/39%_53%_47%_61%] bg-[#FFF9C4]/65 blur-3xl" />
              <div className="absolute right-[18%] bottom-[-6rem] h-80 w-[30rem] rounded-[60%_40%_58%_42%/52%_47%_53%_48%] bg-[#CDEBFF]/55 blur-3xl" />
            </div>

            <div className="relative mx-auto flex h-full max-w-[1720px] gap-3">
              <aside className="hidden h-full w-72 shrink-0 glass-island lg:flex lg:flex-col">
                <div className="border-b border-white/80 px-5 py-5">
                  <span className="inline-flex rounded-2xl bg-[#42A5F5]/22 px-3 py-1 text-xs font-bold tracking-wide text-[#1F5D93] font-montserrat">
                    Holding
                  </span>
                  <h1 className="mt-3 font-signature text-5xl leading-none text-slate-900">Spio</h1>
                  <p className="mt-1 text-xs text-blue-900/60 font-body-copy">Kontrol ringkas.</p>
                </div>

                <SidebarNav />

                <div className="mt-auto border-t border-white/80 px-5 py-4 text-xs font-semibold text-blue-900/60 font-montserrat">v0.1.0</div>
              </aside>

              <main className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">
                <div className="glass-island mb-3 p-4 lg:hidden">
                  <h1 className="font-signature text-4xl leading-none text-slate-900">Spio</h1>
                  <p className="mt-1 text-xs text-blue-900/60 font-body-copy">Kontrol.</p>
                  <SidebarNav compact />
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
              </main>
            </div>
          </div>
        </Providers>
      </body>
    </html>
  );
}
