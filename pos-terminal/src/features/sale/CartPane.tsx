import { Minus, Plus, StickyNote, Trash2 } from "lucide-react";

import { useTextPrompt } from "@/components/ui/TextPromptModal";
import { cancelFiredItemAndNotifyKitchen } from "@/features/restaurant/fire";
import { Money, qty, rs } from "@/lib/money";
import { quoteCart, useSaleStore } from "@/stores/sale";
import { useSessionStore } from "@/stores/session";

export function CartPane() {
  const lines = useSaleStore((s) => s.lines);
  const removeLine = useSaleStore((s) => s.removeLine);
  const setQuantity = useSaleStore((s) => s.setQuantity);
  const updateLine = useSaleStore((s) => s.updateLine);
  const isRestaurant = useSessionStore((s) => s.tenant?.vertical === "restaurant");
  const prompt = useTextPrompt();

  // Removing a cart line. For a restaurant line ALREADY sent to the kitchen we
  // must tell the cook to stop: print a per-item CANCELLED KOT and keep the line
  // struck-through (so the bill shows it too). Un-fired lines are hard-removed.
  async function handleRemove(id: string, sentToKitchen?: boolean) {
    if (isRestaurant && sentToKitchen) {
      const ok = await prompt({
        title: "Cancel this item?",
        description:
          "It was already sent to the kitchen. A CANCELLED ticket will print so the cook stops preparing it, and it will show as CANCELLED on the bill. Confirm to cancel, or dismiss to keep it.",
        confirmLabel: "Cancel item",
        initialValue: "",
      });
      // The prompt resolves null on dismiss; any non-null (incl. "") = confirmed.
      if (ok === null) return;
      await cancelFiredItemAndNotifyKitchen(id);
      return;
    }
    removeLine(id);
  }

  // Edit a line's kitchen note in an in-app modal (Electron's renderer has no
  // working window.prompt, so the old prompt() silently did nothing). updateLine
  // writes the note to the cart so it flows to the KOT + order snapshot on fire,
  // the receipt, and the synced invoice.
  async function editNote(id: string, current: string | null | undefined) {
    const next = await prompt({
      title: "Item note",
      description: "Add a note for the kitchen (e.g. no onions, extra spicy).",
      placeholder: "e.g. no onions",
      initialValue: current ?? "",
      confirmLabel: "Save note",
      multiline: true,
    });
    if (next !== null) updateLine(id, { item_note: next.trim() || null });
  }

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
              <div
                key={line.id}
                className={
                  "flex items-center gap-2 p-3" +
                  (line.cancelled ? " bg-destructive/5" : "")
                }
              >
                <div className="flex-1">
                  <div
                    className={
                      "text-sm font-medium" +
                      (line.cancelled ? " text-destructive line-through" : "")
                    }
                  >
                    {line.product_name}
                    {line.cancelled && (
                      <span className="ml-2 rounded bg-destructive px-1.5 py-0.5 align-middle text-[10px] font-bold not-italic text-destructive-foreground no-underline">
                        CANCELLED
                      </span>
                    )}
                  </div>
                  <div
                    className={
                      "text-xs text-muted-foreground" +
                      (line.cancelled ? " line-through" : "")
                    }
                  >
                    {line.product_sku} · Rs {rs(line.unit_price)}
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
                  {isRestaurant && (
                    <button
                      type="button"
                      onClick={() => editNote(line.id, line.item_note)}
                      className="mt-0.5 inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
                    >
                      <StickyNote className="h-3 w-3" />
                      {line.item_note ? "Edit note" : "Add note"}
                    </button>
                  )}
                  {line.sent_to_kitchen && (
                    <div className="text-[10px] font-medium text-success-soft-foreground">✓ in kitchen</div>
                  )}
                </div>

                {/* Cancelled lines lose their qty steppers — a struck item is
                    not being sold, so its quantity is frozen at what the kitchen
                    was told to stop preparing. */}
                {!line.cancelled && (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      className="flex h-7 w-7 items-center justify-center rounded-md border bg-background hover:bg-muted"
                      onClick={() =>
                        // Restaurant/hotel: no manager approval needed to adjust qty.
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
                      {qty(line.quantity)}
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
                )}

                {/* Line amount at the MENU price (net, tax-exclusive = unit_price
                    × qty). Tax is added once in the totals below, so the cart
                    lines read as real menu prices, not tax-inclusive values. A
                    cancelled line shows Rs 0 struck-through. */}
                <div
                  className={
                    "w-24 text-right font-mono text-sm" +
                    (line.cancelled ? " text-destructive line-through" : "")
                  }
                >
                  Rs {line.net.display()}
                </div>

                {line.cancelled ? (
                  // Undo: re-activate a mistakenly-cancelled line.
                  <button
                    type="button"
                    className="text-xs font-medium text-muted-foreground hover:text-foreground"
                    onClick={() => updateLine(line.id, { cancelled: false })}
                    aria-label="Undo cancel"
                  >
                    Undo
                  </button>
                ) : (
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => handleRemove(line.id, line.sent_to_kitchen)}
                    aria-label="Remove line"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
