import { Banknote, Building2, CreditCard, FileText, Smartphone, Wallet } from "lucide-react";

import type { PaymentMethodCode } from "@/stores/tender";

interface Props {
  enabled: string[];
  selected: PaymentMethodCode | null;
  onSelect: (method: PaymentMethodCode) => void;
}

const METHOD_META: Record<PaymentMethodCode, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  cash:          { label: "Cash",        icon: Banknote },
  card_credit:   { label: "Credit",      icon: CreditCard },
  card_debit:    { label: "Debit",       icon: CreditCard },
  easypaisa:     { label: "EasyPaisa",   icon: Smartphone },
  jazzcash:      { label: "JazzCash",    icon: Smartphone },
  raast:         { label: "Raast",       icon: Smartphone },
  bank_transfer: { label: "Bank xfer",   icon: Building2 },
  store_credit:  { label: "Store credit", icon: Wallet },
  cheque:        { label: "Cheque",      icon: FileText },
};

export function MethodPicker({ enabled, selected, onSelect }: Props) {
  // Keep order from METHOD_META for consistency, filter by enabled.
  const codes = Object.keys(METHOD_META).filter((c) =>
    enabled.includes(c),
  ) as PaymentMethodCode[];

  return (
    <div className="grid grid-cols-3 gap-2">
      {codes.map((code) => {
        const meta = METHOD_META[code];
        const Icon = meta.icon;
        return (
          <button
            key={code}
            type="button"
            onClick={() => onSelect(code)}
            className={`flex h-16 flex-col items-center justify-center rounded-md border text-xs font-medium transition-colors ${
              selected === code
                ? "border-primary bg-primary/5 text-primary"
                : "hover:bg-muted"
            }`}
          >
            <Icon className="h-5 w-5" />
            <span className="mt-1">{meta.label}</span>
          </button>
        );
      })}
    </div>
  );
}
