/**
 * Electron main process.
 *  - Creates the renderer window.
 *  - Opens the SQLite handle and exposes it to the renderer via IPC.
 *  - Spawns the sync worker (utilityProcess) and bridges it to the renderer.
 */

import { BrowserWindow, app } from "electron";
import path from "node:path";

import { initAutoUpdate } from "./auto-update";
import { closeCustomerDisplay, watchDisplayChanges } from "./customer-display";
import { openDb } from "./db/client";
import { registerIpcHandlers } from "./ipc";
import { startSyncWorker, stopSyncWorker } from "./sync/manager";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

function resolveDbPath(): string {
  if (isDev) {
    return path.resolve(process.cwd(), process.env["POS_DB_PATH"] ?? "pos.sqlite");
  }
  return path.join(app.getPath("userData"), "pos.sqlite");
}

function resolveApiBase(): string {
  // electron-vite loads .env/.env.local and statically replaces
  // `import.meta.env.VITE_*` at BUILD time — including in the MAIN process
  // bundle. process.env is NOT populated with VITE_* for the main process, so
  // relying on it alone made pairing/sync silently hit http://localhost:8000
  // ("Could not reach the server"). Prefer the build-time value, then any
  // runtime env override, then the local default.
  const fromBuild = import.meta.env?.VITE_API_URL as string | undefined;
  return fromBuild || process.env["VITE_API_URL"] || "http://localhost:8000";
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1366,
    height: 800,
    minWidth: 1024,
    minHeight: 720,
    autoHideMenuBar: true,
    title: "InvoiceSolution — Terminal",
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  win.webContents.on("preload-error", (_e, p, err) => {
    console.error("[main] preload-error path=", p, "err=", err);
  });

  if (isDev) {
    void win.loadURL(process.env["ELECTRON_RENDERER_URL"]!);
  } else {
    void win.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}

void app.whenReady().then(() => {
  const dbPath = resolveDbPath();
  const apiBase = resolveApiBase();
  openDb(dbPath);
  registerIpcHandlers({ apiBase });
  startSyncWorker({ dbPath, apiBase });
  createWindow();
  // Open customer-facing display on a secondary monitor when present;
  // re-attempts on display hot-plug. No-op for single-display setups.
  watchDisplayChanges();
  // Production-only: check GitHub Releases for a newer build, download
  // in background, install on next quit. Dev mode is a no-op.
  initAutoUpdate();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  stopSyncWorker();
  closeCustomerDisplay();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
