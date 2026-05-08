import { useState } from "react";

import { useProductSearch } from "@/features/catalog/useProducts";

import type { CartLine } from "@/stores/sale";

interface Props {
  onAdd: (line: Omit<CartLine, "id">) => void;
}

export function ProductGrid({ onAdd }: Props) {
  const [query, setQuery] = useState("");
  const { results, loading } = useProductSearch(query);

  return (
    <div className="flex h-full flex-col gap-3">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Scan barcode or search…"
        className="h-12 w-full rounded-md border bg-background px-4 text-base outline-none focus:ring-2 focus:ring-ring"
      />
      <div className="flex-1 overflow-auto pr-1">
        {loading ? (
          <div className="p-4 text-xs text-muted-foreground">Searching…</div>
        ) : results.length === 0 ? (
          <div className="p-4 text-xs text-muted-foreground">
            {query ? "No matches." : "Catalog is empty. Add products in admin web."}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
            {results.map((p) => (
              <button
                key={p.id}
                type="button"
                className="rounded-md border bg-background p-3 text-left transition-transform active:scale-95 hover:bg-muted"
                onClick={() =>
                  onAdd({
                    product_id: p.id,
                    product_name: p.name,
                    product_sku: p.sku,
                    uom_code: p.uom_code,
                    hs_code: null,
                    quantity: "1",
                    unit_price: p.sale_price,
                    discount_pct: "0",
                    discount_amount: "0",
                    tax_rate: p.is_taxable ? "18" : "0",
                    is_taxable: !!p.is_taxable,
                  })
                }
              >
                <div className="line-clamp-2 text-sm font-medium">{p.name}</div>
                <div className="mt-1 text-xs text-muted-foreground">{p.sku}</div>
                <div className="mt-2 font-mono text-sm">Rs. {p.sale_price}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
