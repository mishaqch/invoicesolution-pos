import { create } from "zustand";

/**
 * Mobile sidebar (drawer) open/close state. Desktop (md+) shows the sidebar
 * inline and ignores this. The hamburger in TopBar toggles it; the Sidebar
 * drawer + backdrop read it; clicking a nav link or the backdrop closes it.
 */
interface SidebarState {
  open: boolean;
  toggle: () => void;
  setOpen: (open: boolean) => void;
  close: () => void;
}

export const useSidebarStore = create<SidebarState>((set) => ({
  open: false,
  toggle: () => set((s) => ({ open: !s.open })),
  setOpen: (open) => set({ open }),
  close: () => set({ open: false }),
}));
