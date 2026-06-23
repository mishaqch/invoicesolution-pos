import { Banknote, Building2, CreditCard, ReceiptText, Smartphone, Wallet, Zap } from "lucide-react";

import { Marquee } from "@/components/ui/Marquee";

const METHODS = [
  { icon: Banknote, label: "Cash" },
  { icon: CreditCard, label: "Card" },
  { icon: Smartphone, label: "EasyPaisa" },
  { icon: Smartphone, label: "JazzCash" },
  { icon: Zap, label: "Raast" },
  { icon: Building2, label: "Bank transfer" },
  { icon: ReceiptText, label: "Cheque" },
  { icon: Wallet, label: "Store credit" },
];

/** Scrolling strip of accepted payment methods. */
export function PaymentMarquee() {
  return (
    <div className="container section">
      <div className="mx-auto mb-10 max-w-xl text-center">
        <span className="eyebrow">Payments</span>
        <h2 className="h2 mt-4">Accept every way Pakistan pays</h2>
        <p className="lead mt-3">
          Cash to Raast, wallets to cheques — record it all on one invoice, including split and
          credit sales.
        </p>
      </div>
      <Marquee>
        {METHODS.map((m) => (
          <div
            key={m.label}
            className="flex items-center gap-2.5 rounded-xl border border-slate-100 bg-white px-5 py-3 shadow-soft"
          >
            <m.icon className="h-5 w-5 text-brand-600" />
            <span className="whitespace-nowrap text-sm font-semibold text-ink">{m.label}</span>
          </div>
        ))}
      </Marquee>
    </div>
  );
}
