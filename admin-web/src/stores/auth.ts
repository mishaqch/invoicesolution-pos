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
  // Replace just the tenant slice. Called from the boot-time /auth/me
  // refetch so newly-added fields (logo_url) show up for users whose
  // persisted blob predates a serializer change — without forcing a
  // logout/login. Also covers platform-admin edits to logo / name
  // taking effect on next page load.
  setTenant: (tenant: Tenant | null) => void;
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

      setTenant: (tenant) => set({ tenant }),

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
