/**
 * IPC handlers. Phase 0 only wires meta + queue; auth.pinLogin lives in the
 * renderer (it's a plain HTTPS POST, no native deps needed).
 */

import { ipcMain } from "electron";

import { getDb, getMeta, setMeta } from "./db/client";

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
}
