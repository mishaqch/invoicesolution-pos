import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Role, Tenant, User } from "@pos/shared/types";

interface AuthState {
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
  setTokens: (access: string, refresh: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      user: null,
      tenant: null,
      role: null,

      signIn: ({ access, refresh, user, tenant, role }) =>
        set({ access, refresh, user, tenant, role }),

      setTokens: (access, refresh) => set({ access, refresh }),

      logout: () =>
        set({ access: null, refresh: null, user: null, tenant: null, role: null }),
    }),
    {
      name: "pos-admin-auth",
      partialize: (s) => ({
        access: s.access,
        refresh: s.refresh,
        user: s.user,
        tenant: s.tenant,
        role: s.role,
      }),
    },
  ),
);
