import { ArrowLeft, RefreshCw, RotateCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/components/feedback/Toast";
import { Button } from "@/components/ui/button";

type PendingRow = Awaited<ReturnType<NonNullable<Window["api"]["sync"]>["listPending"]>>[number];

/**
 * Pending-sync queue — what hasn't reached the cloud yet.
 *
 * Reads outbound_queue from local SQLite (so it works offline) and shows every
 * sale still waiting to upload: its local invoice #, amount, attempt count and
 * last error. Failed rows surface first. The cashier can retry one row or kick
 * the whole queue. Auto-refreshes whenever the sync status changes.
 *
 * This makes the offline state legible: during an outage the operator sees
 * exactly what's queued, and watches it drain when the link returns.
 */
export default function SyncPendingRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const toast = useToast();

  const [rows, setRows] = useState<PendingRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    const list = (await window.api?.sync?.listPending?.(200)) ?? [];
    setRows(list);
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
    // Re-pull the list whenever the worker publishes a status change (a row
    // synced, failed, or retried) so the screen tracks the queue live.
    const off = window.api?.sync?.onStatus?.(() => void refresh());
    return () => {
      off?.();
    };
  }, [refresh]);

  async function syncNow() {
    setBusy(true);
    await window.api?.sync?.expedite?.();
    setTimeout(() => void refresh(), 600);
    setBusy(false);
  }

  async function retryRow(id: number) {
    await window.api?.sync?.retryRow?.(id);
    toast.show({ message: t("sync.retry_queued", "Retry queued."), variant: "info" });
    setTimeout(() => void refresh(), 400);
  }

  const pending = rows.filter((r) => r.status !== "failed").length;
  const failed = rows.filter((r) => r.status === "failed").length;

  function chip(status: string) {
    if (status === "failed") return "bg-destructive-soft text-destructive-soft-foreground";
    if (status === "sent") return "bg-warning-soft text-warning-soft-foreground";
    return "bg-warning-soft text-warning-soft-foreground";
  }
  function chipLabel(status: string) {
    if (status === "failed") return t("sync.status_failed", "Failed");
    if (status === "sent") return t("sync.status_sending", "Sending");
    return t("sync.status_pending", "Pending");
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate("/sale", { replace: true })}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> {t("common.back")}
        </button>
        <div className="text-sm font-medium">{t("sync.title", "Pending sync")}</div>
        <Button size="sm" variant="outline" onClick={syncNow} disabled={busy}>
          <RefreshCw className={`mr-1 h-4 w-4 ${busy ? "animate-spin" : ""}`} />
          {t("sync.sync_now", "Sync now")}
        </Button>
      </header>

      <div className="flex shrink-0 items-center gap-4 border-b px-4 py-2 text-xs text-muted-foreground">
        <span>{t("sync.pending_count", "Pending")}: <span className="font-mono">{pending}</span></span>
        <span className={failed > 0 ? "text-destructive" : ""}>
          {t("sync.failed_count", "Failed")}: <span className="font-mono">{failed}</span>
        </span>
      </div>

      <main className="min-h-0 flex-1 overflow-y-auto">
        {loading ? (
          <p className="p-4 text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center">
            <p className="text-sm text-muted-foreground">
              {t("sync.all_synced", "Everything is synced. Nothing waiting to upload.")}
            </p>
          </div>
        ) : (
          <ul className="divide-y">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center gap-3 p-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-mono text-sm">
                      {r.local_invoice_number ?? `${r.entity_type} ${r.client_uuid.slice(0, 8)}`}
                    </span>
                    {r.grand_total && <span className="font-mono text-sm">Rs {r.grand_total}</span>}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className={`rounded-full px-1.5 py-0.5 ${chip(r.status)}`}>{chipLabel(r.status)}</span>
                    {r.attempt_count > 0 && (
                      <span>{t("sync.attempts", "Attempts")}: {r.attempt_count}</span>
                    )}
                    <span>{(r.created_at ?? "").slice(11, 16)}</span>
                  </div>
                  {r.last_error && (
                    <div className="mt-1 truncate text-xs text-destructive" title={r.last_error}>
                      {r.last_error}
                    </div>
                  )}
                </div>
                <Button size="sm" variant="ghost" onClick={() => retryRow(r.id)} title={t("sync.retry", "Retry")}>
                  <RotateCw className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
