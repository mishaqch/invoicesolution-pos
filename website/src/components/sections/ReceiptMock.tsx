/**
 * A stylised FBR receipt rendered in pure markup (no image asset) so it stays
 * crisp at any size and matches the brand. Used as the hero visual.
 */
export function ReceiptMock() {
  return (
    <div className="relative rounded-2xl border border-slate-100 bg-white p-3 shadow-card">
      {/* Browser-ish chrome bar */}
      <div className="mb-3 flex items-center gap-1.5 px-1">
        <span className="h-2.5 w-2.5 rounded-full bg-slate-200" />
        <span className="h-2.5 w-2.5 rounded-full bg-slate-200" />
        <span className="h-2.5 w-2.5 rounded-full bg-slate-200" />
        <span className="ml-2 h-4 flex-1 rounded bg-slate-100" />
      </div>

      <div className="grid gap-3 sm:grid-cols-[1.3fr_1fr]">
        {/* Cart / checkout panel */}
        <div className="rounded-xl bg-slate-50 p-4">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">Checkout</span>
            <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700">
              Terminal 1
            </span>
          </div>
          <ul className="space-y-2.5">
            {[
              ["Tapal Danedar 950g", "Rs 1,250.00"],
              ["Surf Excel 1kg", "Rs 740.00"],
              ["Nestlé Milk Pack ×6", "Rs 1,140.00"],
            ].map(([name, price]) => (
              <li key={name} className="flex items-center justify-between text-[13px]">
                <span className="text-ink-soft">{name}</span>
                <span className="font-mono text-ink">{price}</span>
              </li>
            ))}
          </ul>
          <div className="my-3 border-t border-dashed border-slate-200" />
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-ink">Total</span>
            <span className="font-mono text-base font-bold text-ink">Rs 3,130.00</span>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-1.5">
            {["Cash", "Card", "Raast"].map((m, i) => (
              <div
                key={m}
                className={`rounded-lg px-2 py-1.5 text-center text-[11px] font-medium ${
                  i === 0 ? "bg-brand-600 text-white" : "bg-white text-ink-muted ring-1 ring-slate-200"
                }`}
              >
                {m}
              </div>
            ))}
          </div>
        </div>

        {/* FBR receipt panel */}
        <div className="rounded-xl border border-slate-100 bg-white p-4">
          <div className="text-center">
            <div className="text-[11px] font-bold uppercase tracking-wide text-ink">Tax Invoice</div>
            <div className="mt-0.5 text-[10px] text-ink-muted">FBR Digital Invoicing</div>
          </div>
          <div className="my-3 flex justify-center">
            {/* Faux QR */}
            <div className="grid grid-cols-7 gap-0.5 rounded-lg bg-white p-2 ring-1 ring-slate-200">
              {Array.from({ length: 49 }).map((_, i) => {
                const on = [0, 1, 2, 6, 7, 8, 12, 13, 14, 16, 18, 22, 24, 28, 30, 31, 33, 36, 40, 41, 42, 44, 46, 48].includes(i);
                return (
                  <span
                    key={i}
                    className={`h-1.5 w-1.5 rounded-[1px] ${on ? "bg-ink" : "bg-transparent"}`}
                  />
                );
              })}
            </div>
          </div>
          <div className="space-y-1 text-center">
            <div className="text-[10px] text-ink-muted">FBR Invoice No.</div>
            <div className="font-mono text-[11px] font-semibold text-ink">7000007DI1-...4290</div>
            <div className="mt-2 inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-[10px] font-bold text-brand-700">
              ✓ FBR VALIDATED
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
