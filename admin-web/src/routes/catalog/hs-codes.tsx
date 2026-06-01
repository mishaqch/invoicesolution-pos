import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useHsCodes, useHsCodesMeta } from "@/lib/queries";

// Render "synced just now / X minutes ago / X days ago" from an ISO
// timestamp. Returns null when the sync has never run (placeholder
// copy handles that case in the caller).
function formatSyncedAgo(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  const diffMs = Date.now() - t;
  const min = Math.floor(diffMs / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} minute${min === 1 ? "" : "s"} ago`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

export default function HsCodesBrowser() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useHsCodes(q);
  const { data: meta } = useHsCodesMeta();

  const syncedAgo = formatSyncedAgo(meta?.last_synced_at ?? null);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">HS codes</h1>
      <p className="text-sm text-muted-foreground">
        {meta?.count && meta.count > 1000 ? (
          <>
            Full PRAL HS catalog —{" "}
            <strong>{meta.count.toLocaleString()}</strong> codes
            {syncedAgo && (
              <>, last synced {syncedAgo}</>
            )}
            . Source: <code>/pdi/v1/itemdesccode</code>.
          </>
        ) : (
          <>
            HS catalog{meta?.count ? ` — ${meta.count.toLocaleString()} codes` : ""}.
            Run <code>manage.py sync_pral_reference</code> to pull the full
            ~7,800-code list from PRAL.
          </>
        )}
      </p>
      <Input
        placeholder="Search by code or description…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="max-w-md"
      />
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-32">Code</TableHead>
              <TableHead>Description</TableHead>
              <TableHead className="text-right">Default rate</TableHead>
              <TableHead>UoM</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">No matches.</TableCell></TableRow>
            ) : (
              data?.results.map((h) => (
                <TableRow key={h.code}>
                  <TableCell className="font-mono text-xs">{h.code}</TableCell>
                  <TableCell>{h.description}</TableCell>
                  <TableCell className="text-right font-mono">
                    {h.default_tax_rate ?? "—"}
                  </TableCell>
                  <TableCell>{h.uom_default ?? "—"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
