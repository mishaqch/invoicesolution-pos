import { QueryClient } from "@tanstack/react-query";

/**
 * App-wide React Query client (singleton). Lives in its own module so the auth
 * store can clear its cache on sign-in / lock without a circular import.
 *
 * Retry policy mirrors admin-web: never retry 401/403 (they're "you can't do
 * this", not transient) so an expired session doesn't spam errors; keep the
 * default 3 retries for network blips / 5xx.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error) => {
        const status = (error as { status?: number })?.status;
        if (status === 401 || status === 403) return false;
        return failureCount < 3;
      },
    },
  },
});
