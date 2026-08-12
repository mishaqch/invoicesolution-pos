/**
 * electron-updater wiring — SELF-HOSTED feed.
 *
 * The update feed is our own VPS (electron-builder.yml → publish.provider:
 * generic, url: https://client.invoicesolution.pk/updates/). Each release build
 * emits latest.yml + the .exe + .blockmap; those are uploaded to that URL. Every
 * installed terminal polls it and self-updates — no GitHub, works with a private
 * repo, and we control the rollout.
 *
 * Behavior on the cashier machine:
 *   - Check on startup, then re-check hourly (a till left running all day still
 *     picks up a new release without a restart).
 *   - Update downloads silently in the background.
 *   - Installs on next app quit (autoInstallOnAppQuit) — so it never interrupts
 *     a sale; the new version is live the next time they open the POS.
 *
 * Dev mode (electron-vite dev): autoUpdater is a no-op so you don't
 * accidentally trigger update flows while iterating.
 */

import { BrowserWindow, app, ipcMain } from "electron";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

let initialized = false;
// Set once an update has finished downloading and is staged for install.
let pendingVersion: string | null = null;
let updaterRef: typeof import("electron-updater").autoUpdater | null = null;

function broadcast(channel: string, payload: unknown) {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send(channel, payload);
  }
}

export function initAutoUpdate(): void {
  if (isDev) {
    console.log("[auto-update] dev mode — skipping");
    return;
  }
  if (initialized) return;
  initialized = true;

  let autoUpdater: typeof import("electron-updater").autoUpdater;
  try {
    // Lazy require so dev environments without the dep installed
    // don't crash on import.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    autoUpdater = require("electron-updater").autoUpdater;
  } catch (e) {
    console.warn("[auto-update] electron-updater not installed:", e);
    return;
  }

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  updaterRef = autoUpdater;

  autoUpdater.on("checking-for-update", () => {
    console.log("[auto-update] checking…");
  });
  autoUpdater.on("update-available", (info) => {
    console.log("[auto-update] update available:", info.version);
    // Tell the UI a download has started (so it can show "downloading…").
    broadcast("update:available", { version: info.version });
  });
  autoUpdater.on("update-not-available", () => {
    console.log("[auto-update] up to date");
  });
  autoUpdater.on("download-progress", (p) => {
    broadcast("update:progress", { percent: Math.floor(p.percent) });
  });
  autoUpdater.on("update-downloaded", (info) => {
    console.log(
      "[auto-update] downloaded %s — ready to install on restart",
      info.version,
    );
    pendingVersion = info.version;
    // Tell the UI an update is READY — the cashier gets a banner with a
    // "Restart & update" button (and it also installs on next quit).
    broadcast("update:ready", { version: info.version });
  });
  autoUpdater.on("error", (err) => {
    // Network errors are noisy; we degrade silently. Persistent
    // failures show up in operator logs via Glitchtip (Phase 9).
    console.warn("[auto-update] error:", err.message);
  });

  // Renderer asks "is an update already staged?" (e.g. on a fresh page load).
  ipcMain.handle("update:pending", () => ({ version: pendingVersion }));
  // Renderer clicked "Restart & update now" — quit and install immediately.
  ipcMain.handle("update:install-now", () => {
    if (pendingVersion && updaterRef) {
      // isSilent=false shows the installer briefly; isForceRunAfter relaunches
      // the POS right after so the cashier is back in seconds.
      updaterRef.quitAndInstall(false, true);
    }
    return { ok: !!pendingVersion };
  });

  const check = () =>
    void autoUpdater.checkForUpdates().catch((e) => {
      console.warn("[auto-update] check failed:", e);
    });

  app.on("ready", () => {
    check();
    // Re-check every hour so a machine that stays on all day still updates.
    setInterval(check, 60 * 60 * 1000);
  });
}
