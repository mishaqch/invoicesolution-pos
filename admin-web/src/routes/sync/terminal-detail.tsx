import { ArrowLeft, RotateCw } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useRetrySyncRow, useSyncLog, useSyncStatus, useTerminals } from "@/lib/queries";

export default function TerminalSyncDetail() {
  const { id } = useParams<{ id: string }>();
  const [statusFilter, setStatusFilter] = useState("");
  const { data: status } = useSyncStatus(id);
  const { data: log } = useSyncLog({
    terminal_id: id,
    status: statusFilter || undefined,
  });
  const terminals = useTerminals();
  const retry = useRetrySyncRow();

  const terminal = terminals.data?.results.find((t) => t.id === id);
  const summary = status?.results[0];

  return (
    <div className="space-y-4">
      <Link
        to="/sync"
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="mr-1 h-4 w-4" /> Back to sync health
      </Link>

      <h1 className="text-2xl font-semibold tracking-tight">
        {terminal?.name ?? "Terminal"}
      </h1>

      {summary && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Status</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-3">
            <div>
              <div className="text-muted-foreground">Pending</div>
              <div className="font-mono text-2xl">{summary.pending}</div>
            </div>
            <div>
              <div className="text-muted-foreground">Failed</div>
              <div
                className={`font-mono text-2xl ${
                  summary.failed > 0 ? "text-destructive" : ""
                }`}
              >
                {summary.failed}
              </div>
            </div>
            <div>
              <div className="text-muted-foreground">Last sync</div>
              <div className="text-xs">
                {summary.last_processed_at
                  ? new Date(summary.last_processed_at).toLocaleString()
                  : "—"}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex items-center gap-2">
        <Select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="w-full sm:max-w-xs"
        >
          <option value="">All</option>
          <option value="received">Received (in flight)</option>
          <option value="processed">Processed</option>
          <option value="failed">Failed</option>
          <option value="duplicate">Duplicate</option>
        </Select>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Recent sync events</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Received</TableHead>
                <TableHead className="hidden md:table-cell">Entity</TableHead>
                <TableHead className="hidden lg:table-cell">Action</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden lg:table-cell">Error</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(log?.results ?? []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    No events.
                  </TableCell>
                </TableRow>
              ) : (
                log?.results.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(row.received_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs md:table-cell">{row.entity_type}</TableCell>
                    <TableCell className="hidden font-mono text-xs lg:table-cell">{row.action}</TableCell>
                    <TableCell>
                      <Badge
                        variant={syncStatusVariant(row.status)}
                        title={SYNC_STATUS_HINT[row.status]}
                      >
                        {SYNC_STATUS_LABEL[row.status] ?? row.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden max-w-md text-xs text-muted-foreground lg:table-cell">
                      {row.error_message ?? ""}
                    </TableCell>
                    <TableCell className="text-right">
                      {row.status === "failed" && (
                        <Button
                          size="sm"
                          variant="outline"
                          loading={retry.isPending}
                          onClick={() => retry.mutate(row.id)}
                        >
                          <RotateCw className="mr-1 h-3 w-3" /> Retry
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// Sync-row status mapping. Distinct enum from invoice status — these
// describe whether a row in the outbound terminal-sync queue has been
// accepted, replayed (duplicate), or rejected. Kept inline because
// sync is the only surface that renders it.
const SYNC_STATUS_LABEL: Record<string, string> = {
  processed: "Processed",
  pending: "Pending",
  duplicate: "Duplicate",
  failed: "Failed",
};
const SYNC_STATUS_HINT: Record<string, string> = {
  processed: "Row accepted by the server.",
  pending: "Awaiting upload.",
  duplicate: "Server already saw this client_uuid; treated as a replay.",
  failed: "Upload rejected by the server. Click Retry to re-queue.",
};

function syncStatusVariant(
  s: string,
): "success" | "info" | "warning" | "destructive" | "outline" {
  if (s === "processed") return "success";
  if (s === "duplicate") return "info";
  if (s === "pending") return "warning";
  if (s === "failed") return "destructive";
  return "outline";
}
