import { useIsFetching, useIsMutating } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

/**
 * App-wide top progress bar.
 *
 * Shows ONLY for user-meaningful activity:
 *   - any mutation (save/submit/delete — always user-initiated), and
 *   - INITIAL query loads (a query that is fetching and has no data yet —
 *     i.e. a fresh page/list the user just navigated to).
 *
 * It deliberately IGNORES background refetches of queries that already have
 * data. Several queries poll every 5s (sync status, FBR status, cancel
 * budget); counting those made the bar run nonstop with no user action and
 * "start after the page already opened". `predicate` filters to pending
 * (data-less) fetches so polling never lights the bar.
 *
 * Creep-but-never-finish-until-idle mirrors the YouTube/NProgress pattern.
 */
export function GlobalLoadingBar() {
  // Only count queries that are fetching AND have no data yet (initial load),
  // not background refetches/polls of already-populated queries.
  const initialFetching = useIsFetching({
    predicate: (q) => q.state.fetchStatus === "fetching" && q.state.data === undefined,
  });
  const mutating = useIsMutating();
  const busy = initialFetching + mutating > 0;

  const [width, setWidth] = useState(0);
  const [visible, setVisible] = useState(false);
  const interval = useRef<number | null>(null);

  useEffect(() => {
    if (busy) {
      setVisible(true);
      setWidth((w) => (w === 0 ? 8 : w));
      interval.current = window.setInterval(() => {
        setWidth((w) => (w < 90 ? w + (90 - w) * 0.12 : w));
      }, 200);
      return () => {
        if (interval.current) window.clearInterval(interval.current);
      };
    }
    // Idle → finish + fade. Guard so we don't animate on the very first
    // idle render (nothing was ever in flight).
    if (interval.current) window.clearInterval(interval.current);
    if (!visible) return;
    setWidth(100);
    const t1 = window.setTimeout(() => setVisible(false), 250);
    const t2 = window.setTimeout(() => setWidth(0), 550);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  return (
    <div
      aria-hidden
      className="pointer-events-none fixed left-0 top-0 z-[9999] h-[3px] bg-primary shadow-[0_0_8px_var(--tw-shadow-color)] shadow-primary/70 transition-[width,opacity] duration-200"
      style={{ width: `${width}%`, opacity: visible ? 1 : 0 }}
    />
  );
}
