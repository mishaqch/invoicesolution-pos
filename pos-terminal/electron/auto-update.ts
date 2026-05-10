/**
 * electron-updater wiring.
 *
 * On app start (production builds only) we ask GitHub Releases for a
 * newer version. The auto-update channel is configured in
 * electron-builder.yml (`publish.provider: github`); the deployer
 * supplies GH_TOKEN at release-build time so electron-builder can push
 * the .exe / latest.yml artifacts to a private repo.
 *
 * Behavior on the cashier machine:
 *   - Check on startup (silent, no UI prompt).
 *   - Update is downloaded in the background.
 *   - When ready, a small notification fires; the cashier finishes
 *     their current sale, then we install on next quit.
 *
 * Dev mode (electron-vite dev): autoUpdater is a no-op so you don't
 * accidentally trigger update flows while iterating.
 */

import { app } from "electron";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

let initialized = false;

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

  autoUpdater.on("checking-for-update", () => {
    console.log("[auto-update] checking…");
  });
  autoUpdater.on("update-available", (info) => {
    console.log("[auto-update] update available:", info.version);
  });
  autoUpdater.on("update-not-available", () => {
    console.log("[auto-update] up to date");
  });
  autoUpdater.on("download-progress", (p) => {
    console.log(
      "[auto-update] download progress: %d%%",
      Math.floor(p.percent),
    );
  });
  autoUpdater.on("update-downloaded", (info) => {
    console.log(
      "[auto-update] downloaded %s — will install on next quit",
      info.version,
    );
  });
  autoUpdater.on("error", (err) => {
    // Network errors are noisy; we degrade silently. Persistent
    // failures show up in operator logs via Glitchtip (Phase 9).
    console.warn("[auto-update] error:", err.message);
  });

  app.on("ready", () => {
    void autoUpdater.checkForUpdates().catch((e) => {
      console.warn("[auto-update] initial check failed:", e);
    });
  });
}
