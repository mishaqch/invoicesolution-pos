import { X } from "lucide-react";

import { Money } from "@/lib/money";
import type { Tender } from "@/stores/tender";

const LABELS: Record<string, string> = {
  cash: "Cash",
  card_credit: "Credit",
  card_debit: "Debit",
  easypaisa: "EasyPaisa",
  jazzcash: "JazzCash",
  raast: "Raast",
  bank_transfer: "Bank xfer",
  store_credit: "Store credit",
  cheque: "Cheque",
};

interface Props {
  tenders: Tender[];
  onRemove: (id: string) => void;
}

export function TenderList({ tenders, onRemove }: Props) {
  if (tenders.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-3 text-center text-xs text-muted-foreground">
        No tenders yet. Pick a method above.
      </div>
    );
  }

  return (
    <ul className="divide-y rounded-md border">
      {tenders.map((t) => {
        const label = LABELS[t.payment_method] ?? t.payment_method;
        const ref = t.card_last4
          ? `**${t.card_last4}`
          : t.wallet_transaction_id
          ? `ref ${t.wallet_transaction_id}`
          : t.raast_transaction_id
          ? `ref ${t.raast_transaction_id}`
          : t.bank_reference
          ? `ref ${t.bank_reference}`
          : t.cheque_number
          ? `chq ${t.cheque_number}`
          : "";
        return (
          <li key={t.id} className="flex items-center justify-between p-2 text-sm">
            <div>
              <span className="font-medium">{label}</span>
              {ref && <span className="ml-2 text-xs text-muted-foreground">{ref}</span>}
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono">Rs {Money.fromStr(t.amount).display()}</span>
              <button
                type="button"
                onClick={() => onRemove(t.id)}
                aria-label="Remove tender"
                className="text-muted-foreground hover:text-destructive"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
