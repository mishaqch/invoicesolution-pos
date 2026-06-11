import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useFbrSubmissions,
  useRetrySubmission,
  type FbrSubmissionRow,
} from "@/lib/queries";

export default function SubmissionsPage() {
  const [statusCode, setStatusCode] = useState("");
  const { data } = useFbrSubmissions(statusCode ? { status_code: statusCode } : {});
  const retry = useRetrySubmission();
  const [selected, setSelected] = useState<FbrSubmissionRow | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader title="FBR submissions" />

      <div className="flex items-end gap-2">
        <div>
          <label className="text-xs">Status</label>
          <Select value={statusCode} onChange={(e) => setStatusCode(e.target.value)}>
            <option value="">All</option>
            <option value="00">Valid (00)</option>
            <option value="01">Invalid (01)</option>
          </Select>
        </div>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-sm">Recent submissions</CardTitle></CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>When</TableHead>
                <TableHead className="hidden lg:table-cell">Endpoint</TableHead>
                <TableHead className="hidden md:table-cell">Env</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>FBR #</TableHead>
                <TableHead className="hidden text-right lg:table-cell">Duration</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.results ?? []).length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    No submissions yet.
                  </TableCell>
                </TableRow>
              ) : (
                data?.results.map((row) => (
                  <TableRow key={row.id}>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(row.submitted_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="hidden font-mono text-xs lg:table-cell">{row.endpoint}</TableCell>
                    <TableCell className="hidden md:table-cell">{row.environment}</TableCell>
                    <TableCell>
                      <Badge
                        variant={row.status_code === "00" ? "default" : "destructive"}
                      >
                        {row.status_code ?? "—"}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {row.fbr_invoice_number ?? "—"}
                    </TableCell>
                    <TableCell className="hidden text-right text-xs lg:table-cell">
                      {row.duration_ms ? `${row.duration_ms} ms` : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSelected(row)}
                      >
                        View
                      </Button>
                      {row.status_code !== "00" && row.invoice && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="ml-1"
                          loading={retry.isPending}
                          onClick={() => retry.mutate(row.invoice!)}
                        >
                          Retry
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

      {selected && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Submission detail — {selected.id.slice(0, 8)}…</CardTitle>
              <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                Close
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {selected.error_message && (
              <div className="rounded bg-red-50 p-2 text-xs text-red-900">
                {selected.error_message}
              </div>
            )}
            <details>
              <summary className="cursor-pointer text-sm">Request payload</summary>
              <pre className="mt-2 max-h-72 overflow-auto rounded bg-muted/40 p-3 text-xs">
                {JSON.stringify(
                  (selected as unknown as { request_payload: unknown }).request_payload ?? {},
                  null, 2,
                )}
              </pre>
            </details>
            <details>
              <summary className="cursor-pointer text-sm">Response payload</summary>
              <pre className="mt-2 max-h-72 overflow-auto rounded bg-muted/40 p-3 text-xs">
                {JSON.stringify(
                  (selected as unknown as { response_payload: unknown }).response_payload ?? {},
                  null, 2,
                )}
              </pre>
            </details>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
