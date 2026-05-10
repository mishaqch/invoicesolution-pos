/**
 * Preload script for the customer-display BrowserWindow.
 *
 * Bridges Electron IPC events ("customer-display:message" sent from the
 * main process) into the standard browser `window.postMessage` channel
 * that the customer-display app (customer-display/src/App.tsx) already
 * listens to. This keeps the customer-display app environment-agnostic
 * — it works the same whether driven via Electron IPC or a browser
 * tab's developer console.
 */

import { ipcRenderer } from "electron";

ipcRenderer.on("customer-display:message", (_event, payload) => {
  window.postMessage(payload, "*");
});
