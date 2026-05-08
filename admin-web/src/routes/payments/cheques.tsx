import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  useBounceCheque,
  useCheques,
  useClearCheque,
  type ChequeRow,
} from "@/lib/queries";

export default function ChequesPage() {
  const [statusFilter, setStatusFilter] = useState("pending");
  const { data, isLoading } = useCheques(statusFilter || undefined);
  const clear = useClearCheque();
  const bounce = useBounceCheque();

  const [bouncingId, setBouncingId] = useState<string | null>(null);
  const [bounceReason, setBounceReason] = useState("");

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Cheques</h1>

      <div className="flex items-end gap-3">
        <div>
          <label className="text-xs">Status</label>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="cleared">Cleared</option>
            <option value="bounced">Bounced</option>
          </Select>
        </div>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Cheque #</TableHead>
              <TableHead>Bank</TableHead>
              <TableHead>Date</TableHead>
              <TableHead className="text-right">Amount</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">No cheques.</TableCell></TableRow>
            ) : (
              data?.results.map((c: ChequeRow) => (
                <TableRow key={c.id}>
                  <TableCell className="font-mono text-xs">{c.cheque_number ?? "—"}</TableCell>
                  <TableCell>{c.bank_name ?? "—"}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {c.cheque_date ?? "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono">{c.amount}</TableCell>
                  <TableCell>
                    <Badge variant={
                      c.cheque_status === "cleared" ? "default"
                      : c.cheque_status === "bounced" ? "destructive"
                      : "outline"
                    }>{c.cheque_status ?? "—"}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    {c.cheque_status === "pending" && (
                      <>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => clear.mutate(c.id)}
                          disabled={clear.isPending}
                        >
                          Mark cleared
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="ml-1"
                          onClick={() => { setBouncingId(c.id); setBounceReason(""); }}
                        >
                          Bounce
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {bouncingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-md border bg-background p-6 shadow-lg">
            <h2 className="text-base font-semibold">Mark cheque as bounced</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              The customer will be flagged in their profile. The original FBR
              invoice is left alone — issue a credit note via Returns
              (Phase 6) if needed.
            </p>
            <textarea
              rows={3}
              value={bounceReason}
              onChange={(e) => setBounceReason(e.target.value)}
              placeholder="Reason (e.g. insufficient funds)"
              className="mt-3 w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
            <div className="mt-3 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setBouncingId(null)}>Cancel</Button>
              <Button
                variant="destructive"
                disabled={bounce.isPending}
                onClick={async () => {
                  await bounce.mutateAsync({ id: bouncingId, reason: bounceReason });
                  setBouncingId(null);
                }}
              >
                {bounce.isPending ? "Marking…" : "Mark bounced"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
