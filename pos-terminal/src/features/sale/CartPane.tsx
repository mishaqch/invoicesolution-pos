import { Minus, Plus, Trash2 } from "lucide-react";

import { Money } from "@/lib/money";
import { quoteCart, useSaleStore } from "@/stores/sale";

export function CartPane() {
  const lines = useSaleStore((s) => s.lines);
  const removeLine = useSaleStore((s) => s.removeLine);
  const setQuantity = useSaleStore((s) => s.setQuantity);

  const totals = quoteCart({
    lines,
    cartDiscountPct: useSaleStore.getState().cartDiscountPct,
  });

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-auto">
        {lines.length === 0 ? (
          <div className="p-6 text-center text-sm text-muted-foreground">
            Cart is empty. Tap a product or scan a barcode.
          </div>
        ) : (
          <div className="divide-y">
            {totals.lines.map((line) => (
              <div key={line.id} className="flex items-center gap-2 p-3">
                <div className="flex-1">
                  <div className="text-sm font-medium">{line.product_name}</div>
                  <div className="text-xs text-muted-foreground">
                    {line.product_sku} · Rs {line.unit_price}
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className="flex h-7 w-7 items-center justify-center rounded-md border bg-background hover:bg-muted"
                    onClick={() =>
                      setQuantity(
                        line.id,
                        Money.fromStr(line.quantity).sub(Money.fromStr("1")).toStorageString(),
                      )
                    }
                    disabled={Money.fromStr(line.quantity).le(Money.fromStr("1"))}
                  >
                    <Minus className="h-3 w-3" />
                  </button>
                  <div className="w-10 text-center font-mono text-sm">
                    {line.quantity.replace(/\.0+$/, "")}
                  </div>
                  <button
                    type="button"
                    className="flex h-7 w-7 items-center justify-center rounded-md border bg-background hover:bg-muted"
                    onClick={() =>
                      setQuantity(
                        line.id,
                        Money.fromStr(line.quantity).add(Money.fromStr("1")).toStorageString(),
                      )
                    }
                  >
                    <Plus className="h-3 w-3" />
                  </button>
                </div>

                <div className="w-24 text-right font-mono text-sm">
                  Rs {line.line_total.display()}
                </div>

                <button
                  type="button"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => removeLine(line.id)}
                  aria-label="Remove line"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
