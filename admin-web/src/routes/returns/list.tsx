import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranches, useReturns } from "@/lib/queries";

const REFUND_METHODS = ["", "cash", "store_credit", "card_reversal", "wallet_reversal", "bank_transfer"];

export default function ReturnsList() {
  const [branch, setBranch] = useState("");
  const [refundMethod, setRefundMethod] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const branches = useBranches();
  const { data, isLoading } = useReturns({ branch, refund_method: refundMethod, from, to });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Returns</h1>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
        <div>
          <label className="text-xs">Branch</label>
          <Select value={branch} onChange={(e) => setBranch(e.target.value)}>
            <option value="">All</option>
            {branches.data?.results.map((b) => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </Select>
        </div>
        <div>
          <label className="text-xs">Refund method</label>
          <Select value={refundMethod} onChange={(e) => setRefundMethod(e.target.value)}>
            {REFUND_METHODS.map((m) => (
              <option key={m} value={m}>{m || "All"}</option>
            ))}
          </Select>
        </div>
        <div>
          <label className="text-xs">From</label>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div>
          <label className="text-xs">To</label>
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Return #</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>FBR route</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Refund method</TableHead>
              <TableHead className="text-right">Refund</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">No returns.</TableCell></TableRow>
            ) : (
              data?.results.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">
                    <Link to={`/returns/${r.id}`} className="hover:underline">
                      {r.return_number}
                    </Link>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.return_date}</TableCell>
                  <TableCell>
                    <Badge variant={r.fbr_route === "amend" ? "default" : "secondary"}>
                      {r.fbr_route ?? "—"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">{r.reason.replace("_", " ")}</TableCell>
                  <TableCell className="text-xs">{r.refund_method.replace("_", " ")}</TableCell>
                  <TableCell className="text-right font-mono">Rs {r.refund_amount}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
