import { Plus, Search, Truck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { extractApiErrorMessage } from "@/lib/api";
import { useSaveSupplier, useSuppliers, type Supplier } from "@/lib/queries";

function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

const blank = {
  name: "", contact_person: "", phone: "", email: "", ntn: "", strn: "", address: "",
};

export default function SuppliersList() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [editing, setEditing] = useState<Supplier | "new" | null>(null);

  useEffect(() => { setPage(1); }, [debouncedSearch, pageSize]);

  const params = useMemo(() => {
    const p: Record<string, string> = { page: String(page), page_size: String(pageSize) };
    if (debouncedSearch) p.search = debouncedSearch;
    return p;
  }, [debouncedSearch, page, pageSize]);

  const { data, isLoading, isFetching } = useSuppliers(params);
  const rows = data?.results ?? [];
  const total = data?.count ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Suppliers"
        subtitle="Distributors you buy stock from. Goods receipts reference a supplier so every batch is traceable."
        actions={
          <Button onClick={() => setEditing("new")} className="gap-1">
            <Plus className="h-4 w-4" /> New supplier
          </Button>
        }
      />

      <div className="flex w-full items-center gap-2 sm:max-w-xs">
        <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
        <Input placeholder="Search suppliers…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="hidden md:table-cell">Contact</TableHead>
              <TableHead className="hidden lg:table-cell">Phone</TableHead>
              <TableHead className="hidden xl:table-cell">NTN</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  <Truck className="mx-auto mb-2 h-6 w-6 opacity-50" />
                  No suppliers yet. Add your first distributor.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">
                    {s.name}
                    {/* Phone surfaced inline where its column is hidden. */}
                    {s.phone && (
                      <span className="block font-mono text-[11px] font-normal text-muted-foreground lg:hidden">
                        {s.phone}
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{s.contact_person ?? "—"}</TableCell>
                  <TableCell className="hidden font-mono text-xs lg:table-cell">{s.phone ?? "—"}</TableCell>
                  <TableCell className="hidden font-mono text-xs xl:table-cell">{s.ntn ?? "—"}</TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="outline" onClick={() => setEditing(s)}>Edit</Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Pagination
        page={page} pageSize={pageSize} total={total}
        onPageChange={setPage} onPageSizeChange={setPageSize} loading={isFetching}
      />

      {editing && (
        <SupplierForm
          supplier={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

function SupplierForm({ supplier, onClose }: { supplier: Supplier | null; onClose: () => void }) {
  const save = useSaveSupplier();
  const [values, setValues] = useState({
    name: supplier?.name ?? blank.name,
    contact_person: supplier?.contact_person ?? blank.contact_person,
    phone: supplier?.phone ?? blank.phone,
    email: supplier?.email ?? blank.email,
    ntn: supplier?.ntn ?? blank.ntn,
    strn: supplier?.strn ?? blank.strn,
    address: supplier?.address ?? blank.address,
  });
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof values>(k: K, v: string) {
    setValues((s) => ({ ...s, [k]: v }));
  }

  async function submit() {
    setError(null);
    if (!values.name.trim()) { setError("Name is required."); return; }
    try {
      await save.mutateAsync({
        id: supplier?.id,
        name: values.name.trim(),
        contact_person: values.contact_person || null,
        phone: values.phone || null,
        email: values.email || null,
        ntn: values.ntn || null,
        strn: values.strn || null,
        address: values.address || null,
      });
      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err));
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <Card className="w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <CardHeader>
          <CardTitle>{supplier ? "Edit supplier" : "New supplier"}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Field label="Name" id="s_name">
            <Input id="s_name" value={values.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Contact person" id="s_contact">
              <Input id="s_contact" value={values.contact_person} onChange={(e) => set("contact_person", e.target.value)} />
            </Field>
            <Field label="Phone" id="s_phone">
              <Input id="s_phone" value={values.phone} onChange={(e) => set("phone", e.target.value)} />
            </Field>
            <Field label="NTN" id="s_ntn">
              <Input id="s_ntn" value={values.ntn} onChange={(e) => set("ntn", e.target.value)} />
            </Field>
            <Field label="STRN" id="s_strn">
              <Input id="s_strn" value={values.strn} onChange={(e) => set("strn", e.target.value)} />
            </Field>
          </div>
          <Field label="Email" id="s_email">
            <Input id="s_email" type="email" value={values.email} onChange={(e) => set("email", e.target.value)} />
          </Field>
          <Field label="Address" id="s_address">
            <Input id="s_address" value={values.address} onChange={(e) => set("address", e.target.value)} />
          </Field>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose}>Cancel</Button>
            <Button loading={save.isPending} onClick={submit}>{supplier ? "Save" : "Create"}</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
