import { CalendarClock, CalendarX, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Pagination } from "@/components/ui/pagination";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBranches, useExpiry, type ExpiryRow } from "@/lib/queries";

// Debounce search so we don't query per keystroke.
function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

// Window options: how far ahead to look for expiring stock.
const WINDOWS = [
  { value: "30", label: "Next 30 days" },
  { value: "90", label: "Next 90 days" },
  { value: "180", label: "Next 6 months" },
  { value: "365", label: "Next year" },
];

export default function ExpiryList() {
  const { data: branchData } = useBranches();
  const branches = branchData?.results ?? [];

  const [branch, setBranch] = useState("");          // "" = all branches
  const [within, setWithin] = useState("90");
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search.trim());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  useEffect(() => { setPage(1); }, [branch, within, debouncedSearch, pageSize]);

  const params = useMemo(() => {
    const p: Record<string, string> = {
      page: String(page), page_size: String(pageSize), within,
    };
    if (branch) p.branch = branch;
    if (debouncedSearch) p.q = debouncedSearch;
    return p;
  }, [branch, within, debouncedSearch, page, pageSize]);

  const { data, isLoading, isFetching } = useExpiry(params);
  const rows = data?.results ?? [];
  const total = data?.count ?? 0;
  const expiredCount = rows.filter((r) => r.bucket === "expired").length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Expiry"
        subtitle="Batches in stock that have expired or are nearing expiry — clear or return these."
        actions={
          expiredCount > 0 ? (
            <Badge variant="destructive" className="gap-1 text-sm">
              <CalendarX className="h-4 w-4" /> {expiredCount} expired in view
            </Badge>
          ) : undefined
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex w-full max-w-xs flex-1 items-center gap-2">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          <Input
            placeholder="Search name, SKU or batch…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={within} onChange={(e) => setWithin(e.target.value)} className="w-44">
          {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
        </Select>
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
              <TableHead className="hidden lg:table-cell">Batch</TableHead>
              <TableHead>Expiry</TableHead>
              <TableHead className="text-right">In stock</TableHead>
              <TableHead className="hidden md:table-cell">Branch</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">Loading…</TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  Nothing expiring in this window. Good — stock is fresh.
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.batch_id} className={r.bucket === "expired" ? "bg-destructive/5" : undefined}>
                  <TableCell>
                    <Link to={`/catalog/products/${r.product_id}`} className="font-medium hover:underline">
                      {r.name}
                    </Link>
                    <div className="font-mono text-xs text-muted-foreground">{r.sku}</div>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs lg:table-cell">{r.batch_number}</TableCell>
                  <TableCell className="text-sm">
                    {r.expiry_date}
                    <div className="text-xs text-muted-foreground">{describeDays(r.days_to_expiry)}</div>
                    <span className="block font-mono text-[11px] text-muted-foreground lg:hidden">
                      {r.batch_number}
                    </span>
                  </TableCell>
                  <TableCell className="text-right font-mono">{fmt(r.on_hand)} {r.uom ?? ""}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{r.branch ?? "—"}</TableCell>
                  <TableCell>{statusBadge(r)}</TableCell>
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

function statusBadge(r: ExpiryRow) {
  if (r.bucket === "expired") {
    return (
      <Badge variant="destructive" className="gap-1">
        <CalendarX className="h-3 w-3" /> Expired
      </Badge>
    );
  }
  if (r.bucket === "soon") {
    return (
      <Badge variant="warning" className="gap-1">
        <CalendarClock className="h-3 w-3" /> Expiring soon
      </Badge>
    );
  }
  return <Badge variant="secondary">Upcoming</Badge>;
}

function describeDays(days: number): string {
  if (days < 0) return `${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"} ago`;
  if (days === 0) return "Today";
  return `in ${days} day${days === 1 ? "" : "s"}`;
}

// Trim trailing .0000 for display.
function fmt(s: string): string {
  return s.replace(/\.0+$/, "");
}
