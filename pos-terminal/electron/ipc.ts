/**
 * IPC handlers. Phase 1 adds catalog sync + product list/search.
 */

import { ipcMain } from "electron";

import { getDb, getMeta, setMeta } from "./db/client";
import { listProducts, productsCount, searchProducts, syncCatalog } from "./db/sync";

export function registerIpcHandlers() {
  ipcMain.handle("meta:get", (_e, key: string) => getMeta(key));
  ipcMain.handle("meta:set", (_e, key: string, value: string) => setMeta(key, value));

  ipcMain.handle(
    "queue:enqueue",
    (
      _e,
      entry: {
        client_uuid: string;
        entity_type: string;
        entity_id: string;
        action: string;
        payload: unknown;
      },
    ) => {
      const result = getDb()
        .prepare(
          `INSERT INTO outbound_queue
             (client_uuid, entity_type, entity_id, action, payload, next_attempt_at)
           VALUES (?, ?, ?, ?, ?, datetime('now'))`,
        )
        .run(
          entry.client_uuid,
          entry.entity_type,
          entry.entity_id,
          entry.action,
          JSON.stringify(entry.payload),
        );
      return result.lastInsertRowid as number;
    },
  );

  ipcMain.handle("queue:pending-count", () => {
    const row = getDb()
      .prepare("SELECT COUNT(*) AS n FROM outbound_queue WHERE status = 'pending'")
      .get() as { n: number };
    return row.n;
  });

  // Phase 1
  ipcMain.handle(
    "catalog:sync",
    (_e, opts: { apiBase: string; accessToken: string }) => syncCatalog(opts),
  );
  ipcMain.handle(
    "catalog:search",
    (_e, query: string, limit?: number) => searchProducts(query, limit),
  );
  ipcMain.handle(
    "catalog:list",
    (_e, limit?: number) => listProducts(limit),
  );
  ipcMain.handle("catalog:count", () => productsCount());
}
