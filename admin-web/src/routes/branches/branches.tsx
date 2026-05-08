import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranches, useCreateBranch } from "@/lib/queries";

const PROVINCES = [
  "PUNJAB", "SINDH", "KP", "BALOCHISTAN", "ICT", "GB", "AJK",
] as const;

export default function BranchesList() {
  const { data, isLoading } = useBranches();
  const create = useCreateBranch();
  const [v, setV] = useState({
    name: "", code: "", address: "", city: "", province: "PUNJAB" as const,
  });
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync(v);
      setV({ name: "", code: "", address: "", city: "", province: "PUNJAB" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Branches</h1>

      <Card>
        <CardHeader><CardTitle>Add branch</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid grid-cols-2 gap-3">
            <Field label="Name *"><Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} required /></Field>
            <Field label="Code *"><Input value={v.code} onChange={(e) => setV({ ...v, code: e.target.value })} required /></Field>
            <Field label="City *"><Input value={v.city} onChange={(e) => setV({ ...v, city: e.target.value })} required /></Field>
            <Field label="Province *">
              <Select value={v.province} onChange={(e) => setV({ ...v, province: e.target.value as typeof v.province })}>
                {PROVINCES.map((p) => <option key={p} value={p}>{p}</option>)}
              </Select>
            </Field>
            <div className="col-span-2">
              <Field label="Address *">
                <Input value={v.address} onChange={(e) => setV({ ...v, address: e.target.value })} required />
              </Field>
            </div>
            <div className="col-span-2">
              <Button type="submit" disabled={create.isPending}>
                <Plus className="mr-2 h-4 w-4" /> {create.isPending ? "Adding…" : "Add"}
              </Button>
              {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>City</TableHead>
              <TableHead>Province</TableHead>
              <TableHead>Active</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">No branches yet.</TableCell></TableRow>
            ) : (
              data?.results.map((b) => (
                <TableRow key={b.id}>
                  <TableCell>{b.name}</TableCell>
                  <TableCell className="font-mono text-xs">{b.code}</TableCell>
                  <TableCell>{b.city}</TableCell>
                  <TableCell>{b.province}</TableCell>
                  <TableCell>{b.is_active ? "Yes" : "No"}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
