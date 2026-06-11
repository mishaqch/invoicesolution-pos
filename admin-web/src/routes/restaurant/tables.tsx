import { Grid3x3, Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useBranches,
  useDeleteTable,
  useSaveTable,
  useTables,
  type RestaurantTable,
} from "@/lib/queries";

export default function TablesAdmin() {
  const { data: branchData } = useBranches();
  const branches = branchData?.results ?? [];
  const { data, isLoading } = useTables();
  const del = useDeleteTable();
  const rows = data?.results ?? [];
  const [editing, setEditing] = useState<RestaurantTable | "new" | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Tables"
        subtitle="Define the dine-in tables cashiers can seat orders at."
        actions={
          <Button onClick={() => setEditing("new")} className="gap-1">
            <Plus className="h-4 w-4" /> New table
          </Button>
        }
      />

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead><TableHead>Seats</TableHead>
              <TableHead className="hidden md:table-cell">Zone</TableHead><TableHead className="hidden lg:table-cell">Branch</TableHead><TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  <Grid3x3 className="mx-auto mb-2 h-6 w-6 opacity-50" />
                  No tables yet. Add your first table.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell>{t.seats}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{t.zone ?? "—"}</TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{t.branch_name ?? "—"}</TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button size="sm" variant="outline" onClick={() => setEditing(t)}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => { if (confirm(`Delete table ${t.name}?`)) del.mutate(t.id); }}>Delete</Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {editing && (
        <TableForm
          table={editing === "new" ? null : editing}
          branches={branches}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function TableForm({
  table, branches, onClose,
}: {
  table: RestaurantTable | null;
  branches: { id: string; name: string }[];
  onClose: () => void;
}) {
  const save = useSaveTable();
  const [name, setName] = useState(table?.name ?? "");
  const [seats, setSeats] = useState(String(table?.seats ?? 4));
  const [zone, setZone] = useState(table?.zone ?? "");
  const [branch, setBranch] = useState(table?.branch ?? branches[0]?.id ?? "");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (!name.trim()) { setError("Name is required."); return; }
    if (!branch) { setError("Pick a branch."); return; }
    try {
      await save.mutateAsync({
        id: table?.id, name: name.trim(), seats: Number(seats) || 1,
        zone: zone || null, branch,
      });
      onClose();
    } catch (err) { setError(extractApiErrorMessage(err)); }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <CardHeader><CardTitle>{table ? "Edit table" : "New table"}</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Field label="Name" id="t_name"><Input id="t_name" value={name} onChange={(e) => setName(e.target.value)} placeholder="T1" /></Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Seats" id="t_seats"><NumberInput id="t_seats" mode="integer" value={seats} onChange={setSeats} /></Field>
            <Field label="Zone (optional)" id="t_zone"><Input id="t_zone" value={zone} onChange={(e) => setZone(e.target.value)} placeholder="Rooftop" /></Field>
          </div>
          {branches.length > 1 && (
            <Field label="Branch" id="t_branch">
              <Select id="t_branch" value={branch} onChange={(e) => setBranch(e.target.value)}>
                {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </Select>
            </Field>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button loading={save.isPending} onClick={submit}>{table ? "Save" : "Create"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>;
}
