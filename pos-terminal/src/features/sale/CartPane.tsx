import { Minus, Plus, Trash2 } from "lucide-react";

import { Money } from "@/lib/money";
import { quoteCart, useSaleStore } from "@/stores/sale";
import { useApprovalGate } from "./ApprovalGate";

export function CartPane() {
  const lines = useSaleStore((s) => s.lines);
  const removeLine = useSaleStore((s) => s.removeLine);
  const setQuantity = useSaleStore((s) => s.setQuantity);
  const { requireApproval } = useApprovalGate();

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
                  {/* Restaurant: chosen modifiers + kitchen note under the line. */}
                  {line.modifiers && line.modifiers.length > 0 && (
                    <div className="text-[11px] text-muted-foreground">
                      {line.modifiers.map((m) => m.name).join(", ")}
                    </div>
                  )}
                  {line.item_note && (
                    <div className="text-[11px] italic text-muted-foreground">“{line.item_note}”</div>
                  )}
                  {line.sent_to_kitchen && (
                    <div className="text-[10px] font-medium text-success-soft-foreground">✓ in kitchen</div>
                  )}
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className="flex h-7 w-7 items-center justify-center rounded-md border bg-background hover:bg-muted"
                    onClick={() =>
                      // Reducing a quantity is a partial void → manager approval.
                      requireApproval(
                        {
                          action: "reduce_qty",
                          label: `Reduce qty of ${line.product_name}`,
                          context: {
                            product: line.product_name, sku: line.product_sku,
                            from_qty: line.quantity,
                          },
                        },
                        () =>
                          setQuantity(
                            line.id,
                            Money.fromStr(line.quantity).sub(Money.fromStr("1")).toStorageString(),
                          ),
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
                  onClick={() =>
                    // Removing a line is a void → manager approval (logged).
                    requireApproval(
                      {
                        action: "void_line",
                        label: `Remove ${line.product_name}`,
                        context: {
                          product: line.product_name, sku: line.product_sku,
                          qty: line.quantity, line_total: line.line_total.toStorageString(),
                        },
                      },
                      () => removeLine(line.id),
                    )
                  }
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
