/**
 * App-update banner + status.
 *
 * Two jobs:
 *  1. When a new version has DOWNLOADED, show a prominent bar so the cashier can
 *     apply it in one click (it also auto-installs on next app close).
 *  2. Give VISIBLE feedback about what the updater is doing — checking,
 *     downloading (with %), up-to-date, or errored — so "nothing is happening"
 *     is never a silent mystery. Without this the updater ran invisibly and an
 *     operator had no way to tell whether a terminal was even trying to update.
 *
 * It polls update:info every few seconds (cheap IPC) rather than relying only on
 * the one-shot "ready" event, so it reflects the true state after any reload.
 */
import { useEffect, useState } from "react";

type UpdateInfo = {
  currentVersion: string;
  status: string; // idle | checking | downloading N% | up-to-date | ready X | error: …
  pendingVersion: string | null;
};

type UpdatesApi = {
  pending: () => Promise<{ version: string | null }>;
  info: () => Promise<UpdateInfo>;
  checkNow: () => Promise<{ ok: boolean }>;
  installNow: () => Promise<{ ok: boolean }>;
  onReady: (cb: (info: { version: string }) => void) => () => void;
};
function getUpdatesApi(): UpdatesApi | null {
  return (window as unknown as { api?: { updates?: UpdatesApi } }).api?.updates ?? null;
}

export function UpdateBanner() {
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const [installing, setInstalling] = useState(false);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const api = getUpdatesApi();
    if (!api) return;
    let alive = true;
    const poll = () =>
      api.info().then((i) => { if (alive) setInfo(i); }).catch(() => {});
    void poll();
    const t = setInterval(poll, 5000); // reflect updater state live
    const off = api.onReady(() => void poll());
    return () => {
      alive = false;
      clearInterval(t);
      off();
    };
  }, []);

  const api = getUpdatesApi();
  if (!api || !info) return null;

  const ready = !!info.pendingVersion;
  const status = info.status || "idle";
  const isDownloading = status.startsWith("downloading");
  const isChecking = status === "checking";
  const isError = status.startsWith("error");
  const upToDate = status === "up-to-date";

  async function restart() {
    setInstalling(true);
    try {
      await api!.installNow();
    } catch {
      setInstalling(false);
    }
  }

  async function checkNow() {
    setChecking(true);
    try {
      await api!.checkNow();
      // Give the updater a moment, then refresh the status line.
      setTimeout(() => {
        void api!.info().then(setInfo).catch(() => {});
        setChecking(false);
      }, 2500);
    } catch {
      setChecking(false);
    }
  }

  // READY → prominent primary bar with Restart.
  if (ready) {
    return (
      <div className="fixed inset-x-0 bottom-0 z-50 flex items-center justify-center gap-3 border-t border-primary/40 bg-primary px-4 py-2 text-sm text-primary-foreground shadow-lg print:hidden">
        <span>
          <span className="font-semibold">Update ready</span> — version
          {` ${info.pendingVersion} `}has downloaded. Restart to apply it.
        </span>
        <button
          type="button"
          onClick={restart}
          disabled={installing}
          className="rounded-md bg-primary-foreground px-3 py-1 text-xs font-semibold text-primary hover:opacity-90 disabled:opacity-60"
        >
          {installing ? "Restarting…" : "Restart & update now"}
        </button>
      </div>
    );
  }

  // Otherwise a small, unobtrusive status chip bottom-right with a manual check.
  const label = isDownloading
    ? `Updating… ${status.replace("downloading ", "")}`
    : isChecking
      ? "Checking for updates…"
      : isError
        ? "Update check failed"
        : upToDate
          ? `Up to date (v${info.currentVersion})`
          : `v${info.currentVersion}`;

  const tone = isError
    ? "border-destructive/40 bg-destructive-soft text-destructive-soft-foreground"
    : isDownloading || isChecking
      ? "border-primary/40 bg-primary/5 text-foreground"
      : "border-border bg-background text-muted-foreground";

  return (
    <div className={`fixed bottom-2 right-2 z-40 flex items-center gap-2 rounded-md border px-2.5 py-1 text-xs shadow-sm print:hidden ${tone}`}>
      <span title={isError ? status : undefined}>{label}</span>
      {!isDownloading && !isChecking && (
        <button
          type="button"
          onClick={checkNow}
          disabled={checking}
          className="rounded border border-current/30 px-1.5 py-0.5 font-medium hover:opacity-80 disabled:opacity-50"
        >
          {checking ? "Checking…" : "Check now"}
        </button>
      )}
    </div>
  );
}
