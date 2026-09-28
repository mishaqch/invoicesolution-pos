import { create } from "zustand";
import { persist } from "zustand/middleware";

import { queryClient } from "@/lib/queryClient";

interface AuthState {
  access: string | null;
  refresh: string | null;
  userName: string | null;
  userEmail: string | null;
  role: string | null;

  /** Waiter tapped their name + entered a valid PIN. Clears the query cache so
   *  a previous waiter's cached reads don't leak to the new one. */
  signIn: (payload: {
    access: string;
    refresh: string;
    userName: string;
    userEmail: string;
    role: string | null;
  }) => void;
  setTokens: (access: string, refresh: string) => void;
  /** Lock the terminal: null the tokens + clear the cache, but KEEP the device
   *  pairing. The next screen is the roster/PIN, not re-pairing. */
  lock: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      access: null,
      refresh: null,
      userName: null,
      userEmail: null,
      role: null,

      signIn: ({ access, refresh, userName, userEmail, role }) => {
        queryClient.clear();
        set({ access, refresh, userName, userEmail, role });
      },

      setTokens: (access, refresh) => set({ access, refresh }),

      lock: () => {
        queryClient.clear();
        set({ access: null, refresh: null, userName: null, userEmail: null, role: null });
      },
    }),
    {
      name: "tablet-waiter-auth",
      partialize: (s) => ({
        access: s.access,
        refresh: s.refresh,
        userName: s.userName,
        userEmail: s.userEmail,
        role: s.role,
      }),
    },
  ),
);
