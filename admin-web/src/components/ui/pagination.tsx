import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";

interface PaginationProps {
  /** 1-based current page. */
  page: number;
  /** Rows per page. */
  pageSize: number;
  /** Total row count across all pages (DRF `count`). */
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange?: (size: number) => void;
  pageSizeOptions?: number[];
  /** Disable controls while a fetch is in flight. */
  loading?: boolean;
}

/**
 * Reusable table pagination bar. Server-driven (page/pageSize/total) so it
 * works with DRF's PageNumberPagination — pass the `count` as `total`. Shows
 * the visible range, page X of Y, first/prev/next/last, and an optional
 * rows-per-page selector.
 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [25, 50, 100, 200],
  loading = false,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const clampedPage = Math.min(page, totalPages);
  const from = total === 0 ? 0 : (clampedPage - 1) * pageSize + 1;
  const to = Math.min(clampedPage * pageSize, total);

  const go = (p: number) => {
    const next = Math.min(Math.max(1, p), totalPages);
    if (next !== page) onPageChange(next);
  };

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-xs text-muted-foreground">
        {total === 0
          ? "No results"
          : <>Showing <span className="font-medium text-foreground">{from.toLocaleString()}–{to.toLocaleString()}</span> of <span className="font-medium text-foreground">{total.toLocaleString()}</span></>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {onPageSizeChange && (
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-muted-foreground">Rows</span>
            <Select
              value={String(pageSize)}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="h-8 w-[72px]"
              disabled={loading}
            >
              {pageSizeOptions.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </Select>
          </div>
        )}

        <div className="flex items-center gap-1">
          {/* First/Last are hidden on mobile to avoid the 4-button row
              overflowing narrow phones; Prev/Next always fit. */}
          <Button variant="outline" size="icon" className="hidden h-8 w-8 sm:inline-flex"
            onClick={() => go(1)} disabled={loading || clampedPage <= 1}
            aria-label="First page">
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" className="h-8 w-8"
            onClick={() => go(clampedPage - 1)} disabled={loading || clampedPage <= 1}
            aria-label="Previous page">
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="px-2 text-xs text-muted-foreground whitespace-nowrap">
            Page {clampedPage} of {totalPages}
          </span>
          <Button variant="outline" size="icon" className="h-8 w-8"
            onClick={() => go(clampedPage + 1)} disabled={loading || clampedPage >= totalPages}
            aria-label="Next page">
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon" className="hidden h-8 w-8 sm:inline-flex"
            onClick={() => go(totalPages)} disabled={loading || clampedPage >= totalPages}
            aria-label="Last page">
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
