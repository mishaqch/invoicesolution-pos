import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranches, useInvoices } from "@/lib/queries";

const STATUSES = [
  "", "pending_sync", "submitted", "valid", "failed",
  "cancelled", "partially_cancelled", "finalized",
];

export default function InvoicesList() {
  const [status, setStatus] = useState("");
  const [branch, setBranch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const branches = useBranches();
  const { data, isLoading } = useInvoices({ status, branch, from, to });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Sales</h1>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div className="space-y-1">
          <label className="text-xs">Status</label>
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All"}</option>)}
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-xs">Branch</label>
          <Select value={branch} onChange={(e) => setBranch(e.target.value)}>
            <option value="">All</option>
            {branches.data?.results.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-xs">From</label>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <label className="text-xs">To</label>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice #</TableHead>
              <TableHead>FBR #</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Items</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">
                No invoices match the filters.
              </TableCell></TableRow>
            ) : (
              data?.results.map((i) => (
                <TableRow key={i.id}>
                  <TableCell className="font-mono text-xs">
                    <Link to={`/sales/${i.id}`} className="hover:underline">
                      {i.local_invoice_number}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {i.fbr_invoice_number ?? "—"}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {i.invoice_date}
                  </TableCell>
                  <TableCell>{i.items.length}</TableCell>
                  <TableCell className="text-right font-mono">{i.grand_total}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(i.status)}>{i.status}</Badge>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {data && data.count > 0 && (
        <p className="text-xs text-muted-foreground">{data.count} invoices.</p>
      )}
    </div>
  );
}

function statusVariant(status: string): "default" | "secondary" | "outline" | "destructive" {
  if (status === "valid") return "default";
  if (status === "cancelled" || status === "failed") return "destructive";
  if (status === "finalized") return "secondary";
  return "outline";
}
