/**
 * Preload — exposes a typed `window.api` to the renderer via contextBridge.
 * The renderer never sees `node:` modules or better-sqlite3 directly.
 */

import { contextBridge, ipcRenderer } from "electron";

const api = {
  meta: {
    get: (key: string): Promise<string | null> => ipcRenderer.invoke("meta:get", key),
    set: (key: string, value: string): Promise<void> =>
      ipcRenderer.invoke("meta:set", key, value),
  },
  queue: {
    enqueue: (entry: {
      client_uuid: string;
      entity_type: string;
      entity_id: string;
      action: string;
      payload: unknown;
    }): Promise<number> => ipcRenderer.invoke("queue:enqueue", entry),
    pendingCount: (): Promise<number> => ipcRenderer.invoke("queue:pending-count"),
  },
};

contextBridge.exposeInMainWorld("api", api);

export type PosApi = typeof api;
