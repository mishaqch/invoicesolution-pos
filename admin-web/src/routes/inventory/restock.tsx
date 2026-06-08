import { AlertTriangle, PackageX, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranches, useRestock } from "@/lib/queries";

// Debounce search so we don't query per keystroke.
function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export default function RestockList() {
  const { data: branchData } = useBranches();
  const branches = branchData?.results ?? [];

  const [branch, setBranch] = useState("");          // "" = all branches
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  useEffect(() => { setPage(1); }, [branch, debouncedSearch, pageSize]);

  const params = useMemo(() => {
    const p: Record<string, string> = { page: String(page), page_size: String(pageSize) };
    if (branch) p.branch = branch;
    if (debouncedSearch) p.q = debouncedSearch;
    return p;
  }, [branch, debouncedSearch, page, pageSize]);

  const { data, isLoading, isFetching } = useRestock(params);
  const rows = data?.results ?? [];
  const total = data?.count ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Restock</h1>
          <p className="text-sm text-muted-foreground">
            Products at or below their reorder level — order these soon.
          </p>
        </div>
        {total > 0 && (
          <Badge variant="warning" className="gap-1 text-sm">
            <AlertTriangle className="h-4 w-4" /> {total} need{total === 1 ? "s" : ""} restock
          </Badge>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex max-w-xs flex-1 items-center gap-2">
          <Search className="h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search name or SKU…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        {branches.length > 1 && (
          <Select value={branch} onChange={(e) => setBranch(e.target.value)} className="w-48">
            <option value="">All branches</option>
            {branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </Select>
        )}
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>SKU</TableHead>
              <TableHead className="text-right">In stock</TableHead>
              <TableHead className="text-right">Reorder at</TableHead>
              <TableHead className="text-right">Short by</TableHead>
              <TableHead className="text-right">Suggested order</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">Loading…</TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  {debouncedSearch || branch
                    ? "Nothing needs restocking for this filter."
                    : "All good — no products are below their reorder level."}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.product_id} className={r.out_of_stock ? "bg-destructive/5" : undefined}>
                  <TableCell>
                    <Link to={`/catalog/products/${r.product_id}`} className="font-medium hover:underline">
                      {r.name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.sku}</TableCell>
                  <TableCell className="text-right font-mono">{fmt(r.on_hand)} {r.uom ?? ""}</TableCell>
                  <TableCell className="text-right font-mono text-muted-foreground">{fmt(r.reorder_level)}</TableCell>
                  <TableCell className="text-right font-mono text-amber-600">{fmt(r.shortfall)}</TableCell>
                  <TableCell className="text-right font-mono font-medium">{fmt(r.suggested_order_qty)}</TableCell>
                  <TableCell>
                    {r.out_of_stock ? (
                      <Badge variant="destructive" className="gap-1">
                        <PackageX className="h-3 w-3" /> Out of stock
                      </Badge>
                    ) : (
                      <Badge variant="warning">Low</Badge>
                    )}
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

// Trim trailing .0000 for display.
function fmt(s: string): string {
  return s.replace(/\.0+$/, "");
}
