import { Check, Pause, Receipt, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { NumberInput } from "@/components/ui/number-input";
import { quoteCart, useSaleStore } from "@/stores/sale";
import { useApprovalGate } from "./ApprovalGate";

interface Props {
  onHold: () => void;
}

export function TotalsPane({ onHold }: Props) {
  const navigate = useNavigate();
  const lines = useSaleStore((s) => s.lines);
  const cartDiscountPct = useSaleStore((s) => s.cartDiscountPct);
  const setCartDiscountPct = useSaleStore((s) => s.setCartDiscountPct);
  const customer = useSaleStore((s) => s.customer);
  const resetForNewSale = useSaleStore((s) => s.resetForNewSale);
  const { requireApproval } = useApprovalGate();

  // Discount is TYPED freely but only COMMITTED to the cart via manager
  // approval, so a cashier can't apply any discount unilaterally.
  const [pendingDiscount, setPendingDiscount] = useState(cartDiscountPct);
  useEffect(() => { setPendingDiscount(cartDiscountPct); }, [cartDiscountPct]);
  const discountDirty = pendingDiscount !== cartDiscountPct;

  const totals = quoteCart({ lines, cartDiscountPct });
  const hasItems = lines.length > 0;

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="rounded-md border bg-background p-3">
        <div className="text-xs text-muted-foreground">Customer</div>
        <div className="text-sm">{customer?.name ?? "Walk-in"}</div>
      </div>

      <div className="rounded-md border bg-background p-3">
        <Row label="Subtotal" value={`Rs ${totals.subtotal.display()}`} />
        <Row label="Line discount" value={`- Rs ${totals.line_discount_total.display()}`} muted />

        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-sm text-muted-foreground">Cart discount %</span>
          <div className="flex items-center gap-1">
            <NumberInput
              mode="decimal"
              value={pendingDiscount}
              onChange={setPendingDiscount}
              aria-label="Cart discount percent"
              className="h-8 w-16 text-right"
            />
            <Button
              size="icon"
              variant="outline"
              className="h-8 w-8"
              disabled={!discountDirty}
              aria-label="Apply discount (needs manager approval)"
              onClick={() =>
                requireApproval(
                  {
                    action: "apply_discount",
                    label: `Apply ${pendingDiscount}% cart discount`,
                    context: { discount_pct: pendingDiscount },
                  },
                  () => setCartDiscountPct(pendingDiscount),
                )
              }
            >
              <Check className="h-4 w-4" />
            </Button>
          </div>
        </div>
        <Row label="Cart discount" value={`- Rs ${totals.cart_discount_amount.display()}`} muted />
        <Row label="Tax" value={`Rs ${totals.tax_total.display()}`} />
        <hr className="my-2" />
        <div className="flex items-end justify-between">
          <span className="text-sm font-semibold">TOTAL</span>
          <span className="font-mono text-3xl font-bold">
            Rs {totals.grand_total.display()}
          </span>
        </div>
      </div>

      <Button
        size="lg"
        className="h-16 text-xl"
        disabled={!hasItems}
        onClick={() => navigate("/payment")}
      >
        <Receipt className="mr-2 h-5 w-5" />
        Charge
      </Button>

      <div className="flex gap-2">
        <Button variant="outline" disabled={!hasItems} onClick={onHold} className="flex-1">
          <Pause className="mr-1 h-4 w-4" /> Hold
        </Button>
        <Button
          variant="outline"
          disabled={!hasItems}
          className="flex-1 text-destructive"
          onClick={() =>
            requireApproval(
              {
                action: "void_sale",
                label: "Void the entire sale",
                context: {
                  lines: lines.length,
                  grand_total: totals.grand_total.toStorageString(),
                },
              },
              () => resetForNewSale(),
            )
          }
        >
          <Trash2 className="mr-1 h-4 w-4" /> Void sale
        </Button>
      </div>
    </div>
  );
}

function Row({ label, value, muted }: { label: string; value: string; muted?: boolean }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-mono ${muted ? "text-muted-foreground" : ""}`}>{value}</span>
    </div>
  );
}
