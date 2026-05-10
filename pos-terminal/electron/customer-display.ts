/**
 * Second-monitor customer display.
 *
 * Detects a non-primary display and opens a frameless full-screen
 * BrowserWindow on it pointing at the customer-display app
 * (`customer-display/` package). The cashier's main POS window stays
 * on the primary display.
 *
 * Behavior:
 *   - Single display: no customer window opened. Cashier-side flows
 *     work as normal.
 *   - Multiple displays: customer window opens on the first non-primary
 *     display, frameless, full-screen-ish, no menu, no devtools by
 *     default.
 *   - Hot-plug: a "display-added" event re-attempts to open the window;
 *     "display-removed" closes it gracefully.
 *
 * The renderer talks to the customer display via the IPC channel
 * `customerDisplay:post`. Payload shapes match what
 * customer-display/src/App.tsx expects:
 *   { type: "idle" | "sale" | "qr" | "thanks", ... }
 */

import { BrowserWindow, screen } from "electron";
import path from "node:path";

const isDev = !!process.env["ELECTRON_RENDERER_URL"];

let customerWindow: BrowserWindow | null = null;

function pickSecondaryDisplay() {
  const all = screen.getAllDisplays();
  if (all.length < 2) return null;
  const primary = screen.getPrimaryDisplay();
  return all.find((d) => d.id !== primary.id) ?? null;
}

function customerDisplayUrl(): string {
  // Dev: customer-display dev server on :5175 (configured in
  // customer-display/vite.config.ts).
  // Prod: file: URL into the built customer-display/dist/index.html.
  if (isDev) {
    return process.env["VITE_CUSTOMER_DISPLAY_URL"] ?? "http://localhost:5175";
  }
  return "file://" + path.join(
    __dirname,
    "../../../customer-display/dist/index.html",
  );
}

export function openCustomerDisplay(): BrowserWindow | null {
  if (customerWindow && !customerWindow.isDestroyed()) return customerWindow;
  const secondary = pickSecondaryDisplay();
  if (!secondary) {
    console.log("[customer-display] no secondary display detected; skipping");
    return null;
  }

  console.log(
    "[customer-display] opening on display id=%s (%dx%d at %d,%d)",
    secondary.id,
    secondary.bounds.width,
    secondary.bounds.height,
    secondary.bounds.x,
    secondary.bounds.y,
  );

  customerWindow = new BrowserWindow({
    x: secondary.bounds.x,
    y: secondary.bounds.y,
    width: secondary.bounds.width,
    height: secondary.bounds.height,
    fullscreen: true,
    frame: false,
    autoHideMenuBar: true,
    title: "Pakistan POS — Customer display",
    webPreferences: {
      preload: path.join(__dirname, "customer-display-preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      // sandbox=false because the preload uses ipcRenderer; sandbox
      // forbids node-style IPC. The preload is a few lines and trusted.
      sandbox: false,
    },
  });

  customerWindow.on("closed", () => {
    customerWindow = null;
  });

  void customerWindow.loadURL(customerDisplayUrl());

  return customerWindow;
}

export function closeCustomerDisplay(): void {
  if (customerWindow && !customerWindow.isDestroyed()) {
    customerWindow.close();
  }
  customerWindow = null;
}

export function postToCustomerDisplay(message: unknown): boolean {
  if (!customerWindow || customerWindow.isDestroyed()) return false;
  // Use postMessage so the customer-display app's existing
  // `window.addEventListener("message", ...)` handler picks it up.
  customerWindow.webContents.send("customer-display:message", message);
  return true;
}

export function watchDisplayChanges(): void {
  // Open on startup if a secondary display is already attached.
  openCustomerDisplay();

  screen.on("display-added", () => {
    console.log("[customer-display] display-added; reopening if needed");
    openCustomerDisplay();
  });

  screen.on("display-removed", () => {
    if (customerWindow && !customerWindow.isDestroyed()) {
      const secondary = pickSecondaryDisplay();
      if (!secondary) {
        console.log("[customer-display] secondary display gone; closing");
        closeCustomerDisplay();
      }
    }
  });
}
