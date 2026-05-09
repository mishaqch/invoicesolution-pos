import { type ReactNode } from "react";

import { Sidebar } from "./Sidebar";
import { SyncBanner } from "./SyncBanner";
import { TopBar } from "./TopBar";

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to main content
      </a>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <SyncBanner />
        <main id="main-content" className="flex-1 overflow-auto p-6" role="main">
          {children}
        </main>
      </div>
    </div>
  );
}
