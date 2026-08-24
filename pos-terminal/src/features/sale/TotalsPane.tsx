import { Check, Pause, Receipt, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { NumberInput } from "@/components/ui/number-input";
import { quoteCart, useSaleStore } from "@/stores/sale";

interface Props {
  // Optional: when omitted (restaurant tenants), the generic "Hold" button is
  // hidden. A restaurant order is parked via Send-to-Kitchen into the server
  // "Open orders" book, not the retail held-sales list — mirroring how top POS
  // (Toast/Square) keep fired tickets as live open orders rather than a
  // separate parked bucket. Holding a fired order into the retail bucket would
  // create a duplicate/ghost ticket, so we don't offer it there.
  onHold?: () => void;
}

export function TotalsPane({ onHold }: Props) {
  const navigate = useNavigate();
  const lines = useSaleStore((s) => s.lines);
  const cartDiscountPct = useSaleStore((s) => s.cartDiscountPct);
  const setCartDiscountPct = useSaleStore((s) => s.setCartDiscountPct);
  const customer = useSaleStore((s) => s.customer);
  const resetForNewSale = useSaleStore((s) => s.resetForNewSale);

  // Discount is typed then committed to the cart on tap — no manager approval
  // (restaurant/hotel: cashiers apply discounts directly).
  const [pendingDiscount, setPendingDiscount] = useState(cartDiscountPct);
  useEffect(() => {
    setPendingDiscount(cartDiscountPct);
  }, [cartDiscountPct]);
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
              aria-label="Apply discount"
              onClick={() => setCartDiscountPct(pendingDiscount)}
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
          {/* Display-only: headline total rounded to whole rupees (450.08 →
              "Rs 450"). The stored + FBR amount is unchanged. */}
          <span className="font-mono text-3xl font-bold">
            Rs {totals.grand_total.displayWhole()}
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
        {onHold && (
          <Button variant="outline" disabled={!hasItems} onClick={onHold} className="flex-1">
            <Pause className="mr-1 h-4 w-4" /> Hold
          </Button>
        )}
        <Button
          variant="outline"
          disabled={!hasItems}
          className="flex-1 text-destructive"
          onClick={() => {
            // Restaurant/hotel: cancelling the order needs no manager approval.
            if (window.confirm("Void the entire sale? This clears the cart.")) {
              resetForNewSale();
            }
          }}
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
