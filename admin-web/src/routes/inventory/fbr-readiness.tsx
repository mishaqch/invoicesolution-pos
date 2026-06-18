/**
 * FBR readiness — products not yet invoice-ready.
 *
 * Lists live products whose FBR fiscal identity is incomplete (missing HS code,
 * UoM, sale type, an SRO item serial when a schedule is set, or a retail price
 * for 3rd-Schedule goods). An invoice line for any of these would be rejected
 * by PRAL, and the stock-in gate blocks adding stock for sale until they're
 * fixed — so this is the one place to clear the backlog. Each row links
 * straight to the product editor where the fields live.
 *
 * Available to both POS (`inventory`) and Digital-Invoicing (`warehouses`)
 * tenants, since both submit to FBR.
 */
import { CheckCircle2, FileWarning, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Pagination } from "@/components/ui/pagination";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useFbrReadiness } from "@/lib/queries";

// Debounce search so we don't query per keystroke.
function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export default function FbrReadinessList() {
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  useEffect(() => { setPage(1); }, [debouncedSearch, pageSize]);

  const params = useMemo(() => {
    const p: Record<string, string> = { page: String(page), page_size: String(pageSize) };
    if (debouncedSearch) p.q = debouncedSearch;
    return p;
  }, [debouncedSearch, page, pageSize]);

  const { data, isLoading, isFetching } = useFbrReadiness(params);
  const rows = data?.results ?? [];
  const total = data?.count ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">FBR readiness</h1>
          <p className="text-sm text-muted-foreground">
            Products whose FBR details are incomplete — fix these before invoicing
            or adding stock for sale.
          </p>
        </div>
        {total > 0 ? (
          <Badge variant="warning" className="gap-1 text-sm">
            <FileWarning className="h-4 w-4" /> {total} need{total === 1 ? "s" : ""} attention
          </Badge>
        ) : !isLoading ? (
          <Badge variant="success" className="gap-1 text-sm">
            <CheckCircle2 className="h-4 w-4" /> All invoice-ready
          </Badge>
        ) : null}
      </div>

      <div className="flex max-w-xs items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search name or SKU…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>SKU</TableHead>
              <TableHead className="hidden md:table-cell">HS code</TableHead>
              <TableHead className="hidden lg:table-cell">UoM</TableHead>
              <TableHead>Missing</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">Loading…</TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  {debouncedSearch
                    ? "No incomplete products match this search."
                    : "Every product is invoice-ready — nothing to fix."}
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.product_id}>
                  <TableCell>
                    <Link to={`/catalog/products/${r.product_id}`} className="font-medium hover:underline">
                      {r.name}
                    </Link>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{r.sku}</TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">{r.hs_code || "—"}</TableCell>
                  <TableCell className="hidden text-xs lg:table-cell">{r.uom || "—"}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {r.missing.map((m) => (
                        <Badge key={m} variant="warning" className="text-[11px]">{m}</Badge>
                      ))}
                    </div>
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
