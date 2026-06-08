import { Plus, Search, Trash2, Upload } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDeleteProduct, useProducts, useTenantSetup } from "@/lib/queries";
import { money } from "@/lib/utils";

// Debounce search so we don't fire a request per keystroke against a
// 6000-row catalog.
function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export default function ProductsList() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Any change to the search or page size resets to page 1.
  useEffect(() => { setPage(1); }, [debouncedSearch, pageSize]);

  const params = useMemo(() => {
    const p: Record<string, string> = {
      page: String(page),
      page_size: String(pageSize),
    };
    if (debouncedSearch) p.search = debouncedSearch;
    return p;
  }, [page, pageSize, debouncedSearch]);

  const { data, isLoading, isFetching } = useProducts(params);
  const del = useDeleteProduct();

  // Digital-invoicing tenants (service providers, marriage halls) sell
  // "items" or "services", not "products". Relabel headings + buttons
  // to match their mental model; URLs and API contract are unchanged.
  const { data: setup } = useTenantSetup();
  const di = setup?.business_mode === "digital_invoicing";
  const heading = di ? "Items" : "Products";
  const newLabel = di ? "New item" : "New product";

  const rows = data?.results ?? [];
  const total = data?.count ?? 0;
  const COLS = 7;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">{heading}</h1>
        <div className="flex items-center gap-2">
          <Link to="/catalog/products/import">
            <Button variant="outline" size="sm">
              <Upload className="mr-2 h-4 w-4" /> Import CSV
            </Button>
          </Link>
          <Link to="/catalog/products/new">
            <Button size="sm">
              <Plus className="mr-2 h-4 w-4" /> {newLabel}
            </Button>
          </Link>
        </div>
      </div>

      <div className="flex max-w-md items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search by SKU, barcode, name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>Barcode</TableHead>
              <TableHead>HS code</TableHead>
              <TableHead className="text-right">Sale price</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={COLS} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={COLS} className="text-center text-muted-foreground">
                  {debouncedSearch
                    ? `No products match “${debouncedSearch}”.`
                    : "No products yet. Create one or import a CSV."}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono text-xs">{p.sku}</TableCell>
                  <TableCell>
                    <Link to={`/catalog/products/${p.id}`} className="hover:underline">
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {p.barcode ?? "—"}
                  </TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {p.hs_code ?? "—"}
                  </TableCell>
                  <TableCell className="text-right font-mono">{money(p.sale_price)}</TableCell>
                  <TableCell>
                    {p.is_active ? (
                      <Badge variant="secondary">Active</Badge>
                    ) : (
                      <Badge variant="outline">Inactive</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm(`Delete ${p.name}?`)) del.mutate(p.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Pagination
        page={page}
        pageSize={pageSize}
        total={total}
        onPageChange={setPage}
        onPageSizeChange={setPageSize}
        loading={isFetching}
      />
    </div>
  );
}
