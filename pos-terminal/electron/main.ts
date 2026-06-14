/**
 * Electron main process.
 *  - Creates the renderer window.
 *  - Opens the SQLite handle and exposes it to the renderer via IPC.
 *  - Spawns the sync worker (utilityProcess) and bridges it to the renderer.
 */

import { BrowserWindow, app, dialog, powerMonitor } from "electron";
import { appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";

import { initAutoUpdate } from "./auto-update";
import { closeCustomerDisplay, watchDisplayChanges } from "./customer-display";
import { openDb } from "./db/client";
import { registerIpcHandlers } from "./ipc";
import { expediteWorker, startSyncWorker, stopSyncWorker } from "./sync/manager";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

// --- Startup logging ----------------------------------------------------
// A packaged Windows app that crashes during startup dies SILENTLY — no
// console, no window. To make "installs but won't launch" diagnosable we
// append every startup step + any uncaught error to a log file under the
// user's app-data dir, and surface a hard crash in a native dialog so the
// operator can report it instead of staring at nothing.
function logFilePath(): string {
  try {
    const dir = app.getPath("userData");
    mkdirSync(dir, { recursive: true });
    return path.join(dir, "startup.log");
  } catch {
    return path.join(process.cwd(), "startup.log");
  }
}

function logStartup(message: string): void {
  const line = `[${new Date().toISOString()}] ${message}\n`;
  try {
    appendFileSync(logFilePath(), line);
  } catch {
    /* logging must never throw */
  }
  // eslint-disable-next-line no-console
  console.log(`[startup] ${message}`);
}

// Last-resort handlers: a throw anywhere in main that isn't caught would
// otherwise kill the process with no trace. Log it (and show it once the
// app is ready) instead of vanishing.
process.on("uncaughtException", (err) => {
  logStartup(`UNCAUGHT EXCEPTION: ${err?.stack || err}`);
  try {
    if (app.isReady()) {
      dialog.showErrorBox(
        "InvoiceSolution — startup error",
        `${err?.message || err}\n\nDetails were written to:\n${logFilePath()}`,
      );
    }
  } catch { /* ignore */ }
});
process.on("unhandledRejection", (reason) => {
  logStartup(`UNHANDLED REJECTION: ${reason instanceof Error ? reason.stack : String(reason)}`);
});

// --- Reachability monitor ------------------------------------------------
// The sync worker self-heals within ~2 min via its idle timer + capped network
// backoff, but we want the queue to drain the INSTANT the link returns. We poll
// the backend cheaply and, on an offline→online transition, expedite the worker
// (reset pending backoff + retry now). powerMonitor 'resume' covers laptop wake
// (the classic "stuck in long backoff after sleep" case); the renderer's
// 'online' event (via IPC) is a third, free trigger.
let reachabilityTimer: ReturnType<typeof setInterval> | null = null;
let lastReachable = true; // assume online at boot; first failure flips it

function startReachabilityMonitor(apiBase: string) {
  const base = apiBase.replace(/\/$/, "");
  const check = async () => {
    let reachable = false;
    try {
      // HEAD the API root — any HTTP response (even 401/404) proves the link is
      // up. Only a thrown error (DNS/timeout/refused) counts as unreachable.
      await fetch(base, { method: "HEAD", signal: AbortSignal.timeout(5000) });
      reachable = true;
    } catch {
      reachable = false;
    }
    if (reachable && !lastReachable) {
      // offline → online transition: drain the queue immediately.
      expediteWorker();
    }
    lastReachable = reachable;
  };
  reachabilityTimer = setInterval(() => void check(), 15_000);
  // powerMonitor: resuming from sleep almost always means a fresh network.
  powerMonitor.on("resume", () => expediteWorker());
}

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

// Run a startup step but never let it abort the whole launch. A failure in
// one subsystem (e.g. the sync worker, the reachability poll) must NOT prevent
// the cashier window from opening — the POS has to come up so sales can happen.
// The DB is the one true prerequisite; it's handled separately below.
function safeStep(name: string, fn: () => void): void {
  try {
    logStartup(`step: ${name}`);
    fn();
    logStartup(`ok:   ${name}`);
  } catch (err) {
    logStartup(`FAIL: ${name}: ${err instanceof Error ? err.stack : String(err)}`);
  }
}

void app.whenReady().then(() => {
  logStartup(`app ready (platform=${process.platform}, electron=${process.versions.electron})`);
  const dbPath = resolveDbPath();
  const apiBase = resolveApiBase();

  // The local DB is the one hard prerequisite: without it the POS can't read
  // its catalog or write sales. If it fails (e.g. a native-module ABI
  // mismatch) we can't run — but we must tell the operator clearly with a
  // dialog + log, not die silently.
  try {
    logStartup(`opening DB at ${dbPath}`);
    openDb(dbPath);
    logStartup("DB opened");
  } catch (err) {
    logStartup(`FATAL: openDb failed: ${err instanceof Error ? err.stack : String(err)}`);
    dialog.showErrorBox(
      "InvoiceSolution — cannot start",
      "The local database could not be opened. This usually means a corrupt " +
        "install. Please reinstall the app.\n\nDetails were written to:\n" +
        logFilePath(),
    );
    app.quit();
    return;
  }

  // Window FIRST — so even if a background subsystem below fails, the cashier
  // still gets a working POS screen.
  safeStep("registerIpcHandlers", () => registerIpcHandlers({ apiBase }));
  safeStep("createWindow", () => createWindow());
  // Background subsystems — all non-fatal.
  safeStep("startSyncWorker", () => startSyncWorker({ dbPath, apiBase }));
  safeStep("startReachabilityMonitor", () => startReachabilityMonitor(apiBase));
  // Open customer-facing display on a secondary monitor when present;
  // re-attempts on display hot-plug. No-op for single-display setups.
  safeStep("watchDisplayChanges", () => watchDisplayChanges());
  // Production-only: check GitHub Releases for a newer build, download
  // in background, install on next quit. Dev mode is a no-op.
  safeStep("initAutoUpdate", () => initAutoUpdate());

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("before-quit", () => {
  if (reachabilityTimer) {
    clearInterval(reachabilityTimer);
    reachabilityTimer = null;
  }
  stopSyncWorker();
  closeCustomerDisplay();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
