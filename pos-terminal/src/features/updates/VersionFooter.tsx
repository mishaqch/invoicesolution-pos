/**
 * Small version chip in the corner — shows the installed app version and lets
 * you trigger an update check on demand (for testing/verifying auto-update).
 * Click it to expand a tiny status line ("checking / up-to-date / downloading /
 * ready"). Harmless in production; unobtrusive.
 */
import { useEffect, useState } from "react";

type UpdatesApi = {
  info: () => Promise<{ currentVersion: string; status: string; pendingVersion: string | null }>;
  checkNow: () => Promise<{ ok: boolean }>;
};
function getUpdatesApi(): UpdatesApi | null {
  return (window as unknown as { api?: { updates?: UpdatesApi } }).api?.updates ?? null;
}

export function VersionFooter() {
  const [version, setVersion] = useState<string>("");
  const [status, setStatus] = useState<string>("");
  const [open, setOpen] = useState(false);

  async function refresh() {
    const api = getUpdatesApi();
    if (!api) return;
    try {
      const i = await api.info();
      setVersion(i.currentVersion);
      setStatus(i.status);
    } catch { /* noop */ }
  }

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!version) return null;

  async function checkNow() {
    setStatus("checking…");
    await getUpdatesApi()?.checkNow().catch(() => {});
    setTimeout(refresh, 1500);
  }

  return (
    <div className="fixed bottom-1 right-2 z-40 flex items-center gap-2 text-[10px] text-muted-foreground print:hidden">
      {open && <span className="rounded bg-muted px-1.5 py-0.5">{status || "idle"}</span>}
      <button
        type="button"
        onClick={() => { setOpen((o) => !o); void checkNow(); }}
        className="rounded px-1.5 py-0.5 hover:bg-muted"
        title="App version — click to check for updates"
      >
        v{version}
      </button>
    </div>
  );
}
