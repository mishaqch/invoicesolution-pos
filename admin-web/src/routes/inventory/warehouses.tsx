/**
 * Warehouses (Digital-Invoicing) — manage godowns under each branch.
 *
 * DI wholesalers/distributors track stock per warehouse. This page lists
 * warehouses grouped by branch and lets an owner/manager add one, mark it the
 * branch default, or remove an empty one. Gated by the `warehouses` module +
 * DI business mode in the sidebar, so POS tenants never reach it.
 */
import { Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";

import { useToast } from "@/components/feedback/Toast";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useCreateWarehouse,
  useDeleteWarehouse,
  useUpdateWarehouse,
  useWarehouseBranches,
  useWarehouses,
} from "@/lib/queries";

export default function Warehouses() {
  const { data, isLoading } = useWarehouses();
  const branches = useWarehouseBranches();
  const create = useCreateWarehouse();
  const update = useUpdateWarehouse();
  const del = useDeleteWarehouse();
  const toast = useToast();

  const [branch, setBranch] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [city, setCity] = useState("");
  const [address, setAddress] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const warehouses = data?.results ?? [];
  const branchOpts = branches.data ?? [];

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await create.mutateAsync({ branch, name, code, city, address, is_default: isDefault });
      setName("");
      setCode("");
      setCity("");
      setAddress("");
      setIsDefault(false);
      toast.show({ message: "Warehouse added.", variant: "success" });
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  async function makeDefault(id: string) {
    try {
      await update.mutateAsync({ id, is_default: true });
      toast.show({ message: "Default warehouse updated.", variant: "success" });
    } catch (err) {
      toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
    }
  }

  async function remove(id: string, label: string) {
    if (!window.confirm(`Remove warehouse "${label}"? Its stock must be zero.`)) return;
    try {
      await del.mutateAsync(id);
      toast.show({ message: "Warehouse removed.", variant: "info" });
    } catch (err) {
      toast.show({ message: extractApiErrorMessage(err), variant: "destructive" });
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Warehouses" />

      <Card>
        <CardHeader><CardTitle>Add warehouse</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="wh-branch">Branch *</Label>
              <Select id="wh-branch" value={branch} onChange={(e) => setBranch(e.target.value)} required>
                <option value="">— Select —</option>
                {branchOpts.map((b) => (
                  <option key={b.id} value={b.id}>{b.name} ({b.code})</option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wh-name">Name *</Label>
              <Input id="wh-name" value={name} onChange={(e) => setName(e.target.value)} required placeholder="e.g. Lahore Main Godown" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wh-code">Code *</Label>
              <Input id="wh-code" value={code} onChange={(e) => setCode(e.target.value)} required placeholder="e.g. LHR-1" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="wh-city">City</Label>
              <Input id="wh-city" value={city} onChange={(e) => setCity(e.target.value)} placeholder="e.g. Lahore" />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="wh-address">Address</Label>
              <Input id="wh-address" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="optional" />
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
                Set as the branch default
              </label>
            </div>
            <div className="sm:col-span-2">
              <Button type="submit" loading={create.isPending}>
                <Plus className="mr-2 h-4 w-4" /> {create.isPending ? "Adding…" : "Add warehouse"}
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
              <TableHead>Warehouse</TableHead>
              <TableHead className="hidden md:table-cell">Branch</TableHead>
              <TableHead className="hidden lg:table-cell">Code</TableHead>
              <TableHead className="hidden md:table-cell">City</TableHead>
              <TableHead>Default</TableHead>
              <TableHead className="w-px" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : warehouses.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">No warehouses yet.</TableCell></TableRow>
            ) : (
              warehouses.map((w) => (
                <TableRow key={w.id}>
                  <TableCell>
                    {w.name}
                    <span className="block font-mono text-[11px] text-muted-foreground lg:hidden">{w.code}</span>
                    <span className="block text-[11px] text-muted-foreground md:hidden">{w.branch_name}{w.city ? ` · ${w.city}` : ""}</span>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{w.branch_name}</TableCell>
                  <TableCell className="hidden font-mono text-xs lg:table-cell">{w.code}</TableCell>
                  <TableCell className="hidden md:table-cell">{w.city || "—"}</TableCell>
                  <TableCell>
                    {w.is_default ? (
                      <Badge variant="success" className="gap-1"><Star className="h-3 w-3" /> Default</Badge>
                    ) : (
                      <Button variant="ghost" size="sm" onClick={() => makeDefault(w.id)}>
                        Make default
                      </Button>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="sm" onClick={() => remove(w.id, w.name)}
                      title="Remove (must be empty)">
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
