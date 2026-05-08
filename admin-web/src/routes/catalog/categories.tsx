import { Plus } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { useCategories } from "@/lib/queries";
import { useQueryClient } from "@tanstack/react-query";

export default function CategoriesList() {
  const { data, isLoading } = useCategories();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const slug = name.trim().toLowerCase().replace(/\s+/g, "-").slice(0, 64);
      await api("/catalog/categories/", {
        method: "POST",
        body: JSON.stringify({ name, slug, parent: parent || null }),
      });
      setName("");
      setParent("");
      qc.invalidateQueries({ queryKey: ["categories"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Categories</h1>

      <form onSubmit={add} className="flex items-end gap-3 rounded-md border p-4">
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="name">Name</Label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="parent">Parent</Label>
          <Select id="parent" value={parent} onChange={(e) => setParent(e.target.value)}>
            <option value="">— Top level —</option>
            {data?.results.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </Select>
        </div>
        <Button type="submit" disabled={busy}>
          <Plus className="mr-2 h-4 w-4" /> Add
        </Button>
      </form>
      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Slug</TableHead>
              <TableHead>Parent</TableHead>
              <TableHead>Active</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground text-center">Loading…</TableCell>
              </TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground text-center">No categories yet.</TableCell>
              </TableRow>
            ) : (
              data?.results.map((c) => {
                const parentRow = data.results.find((p) => p.id === c.parent);
                return (
                  <TableRow key={c.id}>
                    <TableCell>{c.name}</TableCell>
                    <TableCell className="font-mono text-xs">{c.slug}</TableCell>
                    <TableCell>{parentRow?.name ?? "—"}</TableCell>
                    <TableCell>{c.is_active ? "Yes" : "No"}</TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
