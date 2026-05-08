import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Role, Tenant, User } from "@pos/shared/types";

interface SessionState {
  access: string | null;
  refresh: string | null;
  user: User | null;
  tenant: Tenant | null;
  role: Role | null;

  signIn: (payload: {
    access: string;
    refresh: string;
    user: User;
    tenant: Tenant | null;
    role: Role | null;
  }) => void;
  logout: () => void;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      user: null,
      tenant: null,
      role: null,

      signIn: ({ access, refresh, user, tenant, role }) =>
        set({ access, refresh, user, tenant, role }),

      logout: () =>
        set({ access: null, refresh: null, user: null, tenant: null, role: null }),
    }),
    {
      name: "pos-terminal-session",
      partialize: (s) => ({ user: s.user, tenant: s.tenant, role: s.role }),
      // Tokens kept in-memory only on the POS — they're short-lived and we
      // don't want them lingering on disk where a swapped terminal could be
      // mined for them. (Phase 3 introduces secure storage if needed.)
    },
  ),
);
