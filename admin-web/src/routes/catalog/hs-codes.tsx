import { useState } from "react";

import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useHsCodes } from "@/lib/queries";

export default function HsCodesBrowser() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useHsCodes(q);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">HS codes</h1>
      <p className="text-sm text-muted-foreground">
        Subset of the FBR catalog (~120 codes). The full ~5000-code list lands later.
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
