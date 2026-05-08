import { type ReactNode } from "react";

import { Sidebar } from "./Sidebar";
import { SyncBanner } from "./SyncBanner";
import { TopBar } from "./TopBar";

export function AdminShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <SyncBanner />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
