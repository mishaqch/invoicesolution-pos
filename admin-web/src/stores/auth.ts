import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { Role, Tenant, User } from "@pos/shared/types";

import { queryClient } from "@/lib/queryClient";

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

      signIn: ({ access, refresh, user, tenant, role }) => {
        // Drop any cached query data from a PREVIOUS session before the new
        // tenant's pages mount — otherwise React Query would briefly serve the
        // prior client's products/invoices/customers (a data-isolation bug when
        // two clients use the same browser).
        queryClient.clear();
        set({ access, refresh, user, tenant, role });
      },

      setTokens: (access, refresh) => set({ access, refresh }),

      setTenant: (tenant) => set({ tenant }),

      logout: () => {
        // Clear the React Query cache so the next sign-in starts clean and no
        // tenant data lingers in memory after sign-out.
        queryClient.clear();
        set({ access: null, refresh: null, user: null, tenant: null, role: null });
      },
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
