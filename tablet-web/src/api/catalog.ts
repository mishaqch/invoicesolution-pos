import { api } from "@/lib/api";
import type { CatalogSyncResponse } from "@/types";

/** GET /api/catalog/sync/?since=<iso?> — full menu (products + categories). */
export function syncCatalog(since?: string): Promise<CatalogSyncResponse> {
  const q = since ? `?since=${encodeURIComponent(since)}` : "";
  return api<CatalogSyncResponse>(`/catalog/sync/${q}`);
}
