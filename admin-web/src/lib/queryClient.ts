import { QueryClient } from "@tanstack/react-query";

/**
 * App-wide React Query client (singleton).
 *
 * Lives in its own module so non-React code — the auth store in particular —
 * can clear the cache on login/logout without importing App.tsx (which would
 * create a circular import). Clearing on auth change is what stops one tenant's
 * cached data (products, invoices, customers…) from showing to the NEXT tenant
 * who logs in on the same browser.
 *
 * Retry policy: never retry 401/403 (they're "you can't do this" answers, not
 * transient failures) so an expired session doesn't spam 4 errors per query;
 * keep the default 3 retries for network blips / 5xx.
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
