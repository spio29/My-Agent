import "./globals.css";
import SidebarNav from "@/components/sidebar-nav";

import Providers from "./providers";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="id">
      <body>
        <Providers>
          <div className="app-shell">
            <aside className="app-sidebar">
              <div className="app-brand">
                <span className="app-brand__name">Portfolio Ops</span>
                <span className="app-brand__meta">Operator workspace</span>
              </div>
              <SidebarNav />
            </aside>

            <main className="app-main">
              <div className="app-mobile-shell">
                <div className="app-mobile-brand">
                  <span className="app-brand__name">Portfolio Ops</span>
                  <span className="app-brand__meta">Operator workspace</span>
                </div>
                <SidebarNav />
              </div>
              <header className="app-header">
                <div>
                  <h1 className="app-title">Operator Workspace</h1>
                  <p className="app-subtitle">
                    Monitor portfolio, workflows, runs, and incidents in one place.
                  </p>
                </div>
              </header>
              <div className="app-content">{children}</div>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
