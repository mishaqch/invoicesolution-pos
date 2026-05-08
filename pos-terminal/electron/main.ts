/**
 * Electron main process.
 *  - Creates the renderer window (fullscreen in prod, windowed in dev).
 *  - Opens the SQLite handle and exposes it to the renderer via IPC (preload).
 */

import { BrowserWindow, app } from "electron";
import path from "node:path";

import { openDb } from "./db/client";
import { registerIpcHandlers } from "./ipc";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

function resolveDbPath(): string {
  // Dev: keep the SQLite next to the project for easy inspection.
  // Prod: Electron's userData folder.
  if (isDev) {
    return path.resolve(process.cwd(), process.env["POS_DB_PATH"] ?? "pos.sqlite");
  }
  return path.join(app.getPath("userData"), "pos.sqlite");
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1366,
    height: 800,
    minWidth: 1024,
    minHeight: 720,
    autoHideMenuBar: true,
    title: "Pakistan POS — Terminal",
    webPreferences: {
      preload: path.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (isDev) {
    void win.loadURL(process.env["ELECTRON_RENDERER_URL"]!);
  } else {
    void win.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
}

void app.whenReady().then(() => {
  openDb(resolveDbPath());
  registerIpcHandlers();
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
