/**
 * Tender store — the list of partial payments accumulated on the
 * /payment screen. Reset whenever a new sale starts.
 */

import { create } from "zustand";

import { Money } from "@/lib/money";

export type PaymentMethodCode =
  | "cash"
  | "card_credit" | "card_debit"
  | "easypaisa" | "jazzcash" | "raast"
  | "bank_transfer" | "store_credit" | "cheque";

export interface Tender {
  /** Local id within the tender list. */
  id: string;
  payment_method: PaymentMethodCode;
  amount: string;  // 4dp Money string

  // Method-specific fields. All optional; the adapter validates them.
  card_last4?: string;
  card_auth_code?: string;
  card_rrn?: string;
  wallet_transaction_id?: string;
  wallet_phone?: string;
  raast_transaction_id?: string;
  raast_iban?: string;
  bank_name?: string;
  bank_account_last4?: string;
  bank_reference?: string;
  cheque_number?: string;
  cheque_date?: string;  // YYYY-MM-DD
}

interface TenderState {
  tenders: Tender[];
  add: (t: Omit<Tender, "id">) => void;
  remove: (id: string) => void;
  reset: () => void;

  totalTendered: () => Money;
  remaining: (grandTotal: Money) => Money;
  isComplete: (grandTotal: Money) => boolean;
}

export const useTenderStore = create<TenderState>((set, get) => ({
  tenders: [],
  add: (t) => set((s) => ({ tenders: [...s.tenders, { ...t, id: crypto.randomUUID() }] })),
  remove: (id) => set((s) => ({ tenders: s.tenders.filter((x) => x.id !== id) })),
  reset: () => set({ tenders: [] }),

  totalTendered: () => {
    return get().tenders.reduce(
      (acc, t) => acc.add(Money.fromStr(t.amount)),
      Money.zero(),
    );
  },
  remaining: (grandTotal) => grandTotal.sub(get().totalTendered()),
  isComplete: (grandTotal) => !get().remaining(grandTotal).isPositive(),
}));
