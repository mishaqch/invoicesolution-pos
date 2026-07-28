import { useEffect, useRef, useState } from "react";

import { useProductSearch } from "@/features/catalog/useProducts";
import { buildCartLineFromProduct } from "@/features/sale/addToCart";
import { rs } from "@/lib/money";

import type { PosCategoryRow, PosProductSqliteRow } from "../../../electron/preload";
import type { CartLine } from "@/stores/sale";

interface Props {
  onAdd: (line: Omit<CartLine, "id">) => void;
  /** Restaurant path: when set, used instead of onAdd so the parent can open a
   *  modifier picker for the product before it lands in the cart. */
  onAddProduct?: (line: Omit<CartLine, "id">, productId: string) => void | Promise<void>;
  /** Branch context for FEFO batch selection on batch-tracked products. */
  branchId?: string | null;
  /** Surface a non-blocking warning (e.g. no/expired batch) to the cashier. */
  onWarn?: (message: string) => void;
  /** Bumped by the parent after a hardware scan so we clear any stray chars
   *  the scanner leaked into the search box and re-focus for the next item. */
  clearSignal?: number;
}

export function ProductGrid({ onAdd, onAddProduct, branchId, onWarn, clearSignal }: Props) {
  const [query, setQuery] = useState("");
  const { results, loading } = useProductSearch(query);
  const inputRef = useRef<HTMLInputElement>(null);

  // Category quick-filter chips (e.g. "Rooms" pinned first for the resort).
  // Shown only when the search box is empty — typing/scanning takes over.
  const [categories, setCategories] = useState<PosCategoryRow[]>([]);
  const [activeCat, setActiveCat] = useState<string | null>(null);
  const [catProducts, setCatProducts] = useState<PosProductSqliteRow[]>([]);

  // Auto-focus on mount so manual typing is immediately usable. The hardware
  // scanner works regardless of focus (window-level listener in sale.tsx), but
  // a focused box is the expected default for keying in a search.
  useEffect(() => {
    inputRef.current?.focus();
    void window.api.catalog
      .categories()
      // Rooms are booked via the Stays / Rooms (Open Stay) flow, not sold as
      // cart items — hide the "Rooms" category chip from the sale page.
      .then((cats) => setCategories(cats.filter((c) => c.name.trim().toLowerCase() !== "rooms")))
      .catch(() => setCategories([]));
  }, []);

  // Clear + re-focus after a scan (parent bumps clearSignal). Skip the initial
  // render so we don't fight the mount auto-focus.
  const firstClear = useRef(true);
  useEffect(() => {
    if (firstClear.current) {
      firstClear.current = false;
      return;
    }
    setQuery("");
    inputRef.current?.focus();
  }, [clearSignal]);

  // Load the active category's products. Typing a search clears the category.
  useEffect(() => {
    if (query.trim()) {
      setActiveCat(null);
      return;
    }
    if (!activeCat) {
      setCatProducts([]);
      return;
    }
    void window.api.catalog.byCategory(activeCat, 200).then(setCatProducts).catch(() => setCatProducts([]));
  }, [activeCat, query]);

  // What the grid shows: search results if searching, else the picked
  // category's products, else the default recent list.
  const searching = !!query.trim();
  const grid = searching ? results : activeCat ? catProducts : results;

  return (
    <div className="flex h-full flex-col gap-3">
      <input
        ref={inputRef}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Scan barcode or search…"
        className="h-12 w-full rounded-md border bg-background px-4 text-base outline-none focus:ring-2 focus:ring-ring"
      />

      {!searching && categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setActiveCat(null)}
            className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
              activeCat === null ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
            }`}
          >
            All
          </button>
          {categories.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setActiveCat(c.id)}
              className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                activeCat === c.id ? "border-primary bg-primary text-primary-foreground" : "bg-background hover:bg-muted"
              }`}
            >
              {c.name}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1 overflow-auto pr-1">
        {loading && searching ? (
          <div className="p-4 text-xs text-muted-foreground">Searching…</div>
        ) : grid.length === 0 ? (
          <div className="p-4 text-xs text-muted-foreground">
            {searching ? "No matches." : activeCat ? "No items in this category." : "Catalog is empty. Add products in admin web."}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
            {grid.map((p) => (
              <button
                key={p.id}
                type="button"
                className="rounded-md border bg-background p-3 text-left transition-transform active:scale-95 hover:bg-muted"
                onClick={() => {
                  void (async () => {
                    // Route through the shared helper so the tap path carries
                    // the real HS code AND a FEFO batch (for batch-tracked
                    // products), exactly like the barcode-scan path.
                    const { line, warning } = await buildCartLineFromProduct(p, { branchId });
                    if (onAddProduct) {
                      await onAddProduct(line as Omit<CartLine, "id">, p.id);
                    } else {
                      onAdd(line as Omit<CartLine, "id">);
                    }
                    if (warning) onWarn?.(warning);
                  })();
                }}
              >
                <div className="line-clamp-2 text-sm font-medium">{p.name}</div>
                <div className="mt-1 text-xs text-muted-foreground">{p.sku}</div>
                <div className="mt-2 font-mono text-sm">Rs. {rs(p.sale_price)}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
