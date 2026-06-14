/**
 * Sync status indicator for the POS header.
 *   green:  queue empty AND last successful sync < 60s ago
 *   amber:  queue non-empty, syncing in progress
 *   red:    any failed row OR (last successful > 5min ago && pending > 0)
 *
 * Tap to expand into a small popover with manual "Sync now" + retry-failed.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

interface Status {
  counts: { pending: number; ok: number; failed: number };
  last_processed_at: string | null;
  last_error: string | null;
}

type Color = "green" | "amber" | "red" | "idle";

function colorFor(s: Status): Color {
  if (s.counts.failed > 0) return "red";
  if (s.counts.pending > 0) {
    const last = s.last_processed_at ? new Date(s.last_processed_at).getTime() : 0;
    if (Date.now() - last > 5 * 60 * 1000 && last > 0) return "red";
    return "amber";
  }
  if (!s.last_processed_at) return "idle";
  const last = new Date(s.last_processed_at).getTime();
  if (Date.now() - last < 60 * 1000) return "green";
  return "idle";
}

export function SyncStatusDot() {
  const [status, setStatus] = useState<Status>({
    counts: { pending: 0, ok: 0, failed: 0 },
    last_processed_at: null,
    last_error: null,
  });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (!window.api?.sync) return;
    let cancelled = false;
    void window.api.sync.status().then((s) => {
      if (!cancelled) setStatus(s);
    });
    const off = window.api.sync.onStatus((s) => setStatus(s));
    return () => {
      cancelled = true;
      off();
    };
  }, []);

  const color = colorFor(status);

  // Semantic tokens — these track WCAG-tuned contrast values defined
  // in src/index.css. Matches admin-web's invoice-status palette so
  // operators see the same green/amber/red across surfaces.
  const colorClass: Record<Color, string> = {
    green: "bg-success",
    amber: "bg-warning",
    red: "bg-destructive",
    idle: "bg-muted-foreground/40",
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-muted"
        title="Sync status"
        aria-label="Sync status"
      >
        <span className={`h-2.5 w-2.5 rounded-full ${colorClass[color]}`} />
        {status.counts.pending > 0 && (
          <span className="text-xs text-muted-foreground">{status.counts.pending}</span>
        )}
        {status.counts.failed > 0 && (
          <span className="rounded-full bg-destructive-soft px-1.5 text-xs text-destructive-soft-foreground">
            {status.counts.failed}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-9 z-10 w-72 rounded-md border bg-background p-3 shadow-md">
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Pending</span>
              <span className="font-mono">{status.counts.pending}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Synced</span>
              <span className="font-mono">{status.counts.ok}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Failed</span>
              <span className={`font-mono ${status.counts.failed > 0 ? "text-destructive" : ""}`}>
                {status.counts.failed}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Last sync</span>
              <span className="font-mono text-xs">
                {status.last_processed_at
                  ? new Date(status.last_processed_at).toLocaleTimeString()
                  : "—"}
              </span>
            </div>
            {status.last_error && (
              <div className="mt-2 rounded bg-destructive-soft p-2 text-xs text-destructive-soft-foreground">
                {status.last_error}
              </div>
            )}
          </div>

          <div className="mt-3 flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                // expedite (not kick): reset any backoff and retry now, so a
                // manual "Sync now" drains the queue even mid-outage-backoff.
                await window.api.sync.expedite();
                setBusy(false);
              }}
              className="flex-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
            >
              Sync now
            </button>
            {status.counts.failed > 0 && (
              <button
                type="button"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  await window.api.sync.retryFailed();
                  setBusy(false);
                }}
                className="flex-1 rounded-md border px-2 py-1 text-xs text-warning-soft-foreground hover:bg-muted"
              >
                Retry failed
              </button>
            )}
          </div>

          {(status.counts.pending > 0 || status.counts.failed > 0) && (
            <button
              type="button"
              onClick={() => { setOpen(false); navigate("/sync"); }}
              className="mt-2 w-full rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              View pending →
            </button>
          )}
        </div>
      )}
    </div>
  );
}
