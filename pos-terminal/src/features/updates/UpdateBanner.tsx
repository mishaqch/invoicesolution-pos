/**
 * App-update banner. When a new terminal version has downloaded in the
 * background, this shows a small bar so the cashier KNOWS an update is waiting
 * and can apply it with one click — instead of silently waiting for them to
 * happen to quit and reopen.
 *
 * The update also installs automatically on the next app close, so ignoring the
 * banner is safe; this just lets them apply it now (e.g. between customers).
 */
import { useEffect, useState } from "react";

// window.api.updates is only present in the Electron build; guard for dev/web.
type UpdatesApi = {
  pending: () => Promise<{ version: string | null }>;
  installNow: () => Promise<{ ok: boolean }>;
  onReady: (cb: (info: { version: string }) => void) => () => void;
};
function getUpdatesApi(): UpdatesApi | null {
  return (window as unknown as { api?: { updates?: UpdatesApi } }).api?.updates ?? null;
}

export function UpdateBanner() {
  const [version, setVersion] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    const api = getUpdatesApi();
    if (!api) return;
    // An update may already be staged (e.g. downloaded before this page loaded).
    void api.pending().then((r) => { if (r.version) setVersion(r.version); }).catch(() => {});
    // ...and listen for one that finishes while the app is open.
    const off = api.onReady((info) => setVersion(info.version));
    return off;
  }, []);

  if (!version) return null;

  async function restart() {
    setInstalling(true);
    try {
      await getUpdatesApi()?.installNow();
    } catch {
      setInstalling(false);
    }
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-50 flex items-center justify-center gap-3 border-t border-primary/40 bg-primary px-4 py-2 text-sm text-primary-foreground shadow-lg print:hidden">
      <span>
        <span className="font-semibold">Update ready</span> — a new version
        {` (${version}) `}has downloaded. Restart to apply it.
      </span>
      <button
        type="button"
        onClick={restart}
        disabled={installing}
        className="rounded-md bg-primary-foreground px-3 py-1 text-xs font-semibold text-primary hover:opacity-90 disabled:opacity-60"
      >
        {installing ? "Restarting…" : "Restart & update now"}
      </button>
      <button
        type="button"
        onClick={() => setVersion(null)}
        className="rounded-md border border-primary-foreground/40 px-2 py-1 text-xs hover:bg-primary-foreground/10"
        title="Dismiss — the update still installs when you next close the app"
      >
        Later
      </button>
    </div>
  );
}
