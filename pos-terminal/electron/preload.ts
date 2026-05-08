/**
 * Preload — exposes a typed `window.api` to the renderer via contextBridge.
 * The renderer never sees `node:` modules or better-sqlite3 directly.
 */

import { contextBridge, ipcRenderer } from "electron";

export interface PosProductSqliteRow {
  id: string;
  category_id: string | null;
  sku: string;
  barcode: string | null;
  name: string;
  name_ur: string | null;
  uom_code: string;
  tax_rate_id: string | null;
  is_taxable: number;
  sale_price: string;
  retail_price: string | null;
  min_sale_price: string | null;
  max_discount_pct: string | null;
  is_weighable: number;
  image_url: string | null;
  is_active: number;
  updated_at: string;
  deleted_at: string | null;
}

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
  catalog: {
    sync: (opts: { apiBase: string; accessToken: string }): Promise<{
      products: number;
      categories: number;
    }> => ipcRenderer.invoke("catalog:sync", opts),
    search: (query: string, limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:search", query, limit),
    list: (limit?: number): Promise<PosProductSqliteRow[]> =>
      ipcRenderer.invoke("catalog:list", limit),
    count: (): Promise<number> => ipcRenderer.invoke("catalog:count"),
  },
};

contextBridge.exposeInMainWorld("api", api);

export type PosApi = typeof api;
