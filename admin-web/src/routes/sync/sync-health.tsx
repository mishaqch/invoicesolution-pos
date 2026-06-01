import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useSyncStatus, useTerminals } from "@/lib/queries";

export default function SyncHealth() {
  const { data: status } = useSyncStatus();
  const { data: terminals } = useTerminals();

  const byId = new Map(
    terminals?.results.map((t) => [t.id, t]) ?? [],
  );

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sync health</h1>
        <p className="text-sm text-muted-foreground">
          Live status of every terminal's outbound queue. Auto-refreshes
          every 5 seconds.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Terminals</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Terminal</TableHead>
                <TableHead>Branch</TableHead>
                <TableHead>Pending</TableHead>
                <TableHead>Failed</TableHead>
                <TableHead>Last sync</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(status?.results ?? []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    No terminals registered yet.
                  </TableCell>
                </TableRow>
              ) : (
                status?.results.map((s) => {
                  const t = byId.get(s.terminal);
                  return (
                    <TableRow key={s.terminal}>
                      <TableCell>
                        {t?.name ?? s.terminal}
                        {t?.terminal_index != null && (
                          <span className="ml-1 font-mono text-xs text-muted-foreground">
                            (T{t.terminal_index})
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {t?.branch.slice(0, 8) ?? "—"}…
                      </TableCell>
                      <TableCell className="font-mono">
                        {s.pending}
                      </TableCell>
                      <TableCell className="font-mono">
                        {s.failed > 0 ? (
                          <Badge variant="destructive">{s.failed}</Badge>
                        ) : (
                          0
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {s.last_processed_at
                          ? new Date(s.last_processed_at).toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <Link
                          to={`/sync/terminals/${s.terminal}`}
                          className="text-xs underline-offset-2 hover:underline"
                        >
                          View log
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
