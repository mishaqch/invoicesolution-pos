/**
 * Method-specific sub-flow forms. Each one calls `onAdd(tender)` when the
 * cashier clicks "Add tender". Validation happens both here (UX) and on
 * the server when the sale is finalized.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NumberInput } from "@/components/ui/number-input";
import { Select } from "@/components/ui/select";
import { Money } from "@/lib/money";

import type { PaymentMethodConfig } from "./usePaymentMethods";
import type { Tender } from "@/stores/tender";

const PK_BANKS = [
  "HBL", "MCB", "UBL", "Allied",
  "Meezan", "Faysal", "BankAlfalah", "Soneri",
  "Askari", "Standard Chartered", "BankIslami",
  "Habib Metropolitan", "Other",
];

interface Props {
  remaining: Money;
  config: PaymentMethodConfig;
  storeCredit: Money;     // 0 if no customer or no credit
  hasCustomer: boolean;
  onAdd: (t: Omit<Tender, "id">) => void;
}

interface AmountFieldProps {
  amount: string;
  setAmount: (s: string) => void;
  remaining: Money;
}

function AmountField({ amount, setAmount, remaining }: AmountFieldProps) {
  return (
    <div>
      <Label>Amount</Label>
      <NumberInput
        mode="decimal"
        value={amount}
        onChange={setAmount}
        placeholder={remaining.display()}
        className="font-mono"
        aria-label="Tender amount"
      />
      <div className="mt-2 flex flex-wrap gap-1">
        <Button
          variant="outline" size="sm" type="button"
          onClick={() => setAmount(remaining.toStorageString())}
        >
          Remaining (Rs {remaining.display()})
        </Button>
      </div>
    </div>
  );
}

export function CashSubFlow({ remaining, onAdd }: Props) {
  const [amount, setAmount] = useState("");
  const tend = amount ? Money.fromStr(amount) : Money.zero();
  const change = tend.sub(remaining);

  return (
    <div className="space-y-3">
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      {change.isPositive() && (
        <div className="rounded bg-success-soft text-success-soft-foreground p-2 text-sm">
          Change: <span className="font-mono">Rs {change.display()}</span>
        </div>
      )}
      <Button
        className="w-full" disabled={!amount || tend.isNegative() || tend.isZero()}
        onClick={() => onAdd({
          payment_method: "cash",
          amount: tend.gt(remaining) ? remaining.toStorageString() : tend.toStorageString(),
        })}
      >
        Add cash tender
      </Button>
      <p className="text-xs text-muted-foreground">
        If you tender more than the remaining, the difference is treated as
        change handed back; only the remaining amount is recorded.
      </p>
    </div>
  );
}

export function CardSubFlow({
  remaining, onAdd, kind,
}: Props & { kind: "card_credit" | "card_debit" }) {
  const [amount, setAmount] = useState(remaining.toStorageString());
  const [last4, setLast4] = useState("");
  const [authCode, setAuthCode] = useState("");
  const [rrn, setRrn] = useState("");
  const [skipRrn, setSkipRrn] = useState(false);

  const valid = /^\d{4}$/.test(last4) && /^\d{6}$/.test(authCode);

  return (
    <div className="space-y-3">
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label>Last 4</Label>
          <NumberInput
            mode="integer" maxLength={4}
            value={last4} onChange={setLast4}
            aria-label="Card last 4 digits"
          />
        </div>
        <div>
          <Label>Auth code</Label>
          <NumberInput
            mode="integer" maxLength={6}
            value={authCode} onChange={setAuthCode}
            aria-label="Card auth code"
          />
        </div>
      </div>
      {!skipRrn ? (
        <div>
          <div className="flex items-center justify-between">
            <Label>RRN</Label>
            <button
              type="button"
              className="text-xs text-muted-foreground underline-offset-2 hover:underline"
              onClick={() => { setSkipRrn(true); setRrn(""); }}
            >
              Skip RRN
            </button>
          </div>
          <NumberInput
            mode="integer"
            value={rrn} onChange={setRrn}
            aria-label="Card RRN"
          />
        </div>
      ) : (
        <button
          type="button"
          className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          onClick={() => setSkipRrn(false)}
        >
          Add RRN after all
        </button>
      )}
      <Button
        className="w-full" disabled={!valid || !amount}
        onClick={() => onAdd({
          payment_method: kind,
          amount,
          card_last4: last4,
          card_auth_code: authCode,
          card_rrn: rrn || undefined,
        })}
      >
        Add card tender
      </Button>
    </div>
  );
}

export function WalletSubFlow({
  remaining, onAdd, config, kind,
}: Props & { kind: "easypaisa" | "jazzcash" }) {
  const [amount, setAmount] = useState(remaining.toStorageString());
  const [txId, setTxId] = useState("");
  const [phone, setPhone] = useState("");
  const qr = kind === "easypaisa" ? config.easypaisa_qr_url : config.jazzcash_qr_url;

  return (
    <div className="space-y-3">
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      {qr ? (
        <div className="rounded-md border bg-muted/30 p-3 text-center">
          <img src={qr} alt="Merchant QR" className="mx-auto h-44 w-44 rounded" />
          <p className="mt-2 text-xs text-muted-foreground">
            Customer scans this with their {kind === "easypaisa" ? "EasyPaisa" : "JazzCash"} app
          </p>
        </div>
      ) : (
        <p className="rounded bg-warning-soft p-2 text-xs text-warning-soft-foreground">
          No QR configured. Set the QR image URL under admin → Payment methods.
        </p>
      )}
      <div>
        <Label>Reference / transaction ID</Label>
        <Input
          value={txId} onChange={(e) => setTxId(e.target.value)}
          placeholder="From the customer's app"
        />
      </div>
      <div>
        <Label>Customer phone (optional)</Label>
        <NumberInput
          mode="integer" maxLength={11}
          value={phone} onChange={setPhone}
          placeholder="03001234567"
          aria-label="Customer phone"
        />
      </div>
      <Button
        className="w-full" disabled={!amount || !txId.trim()}
        onClick={() => onAdd({
          payment_method: kind, amount,
          wallet_transaction_id: txId.trim(),
          wallet_phone: phone.trim() || undefined,
        })}
      >
        Add tender
      </Button>
    </div>
  );
}

export function RaastSubFlow({ remaining, onAdd, config }: Props) {
  const [amount, setAmount] = useState(remaining.toStorageString());
  const [txId, setTxId] = useState("");

  return (
    <div className="space-y-3">
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      {config.raast_qr_url ? (
        <div className="rounded-md border bg-muted/30 p-3 text-center">
          <img src={config.raast_qr_url} alt="Raast QR" className="mx-auto h-44 w-44 rounded" />
          <p className="mt-2 text-xs text-muted-foreground">
            Customer scans with any banking app
          </p>
        </div>
      ) : (
        <p className="rounded bg-warning-soft p-2 text-xs text-warning-soft-foreground">
          No Raast QR configured. Set it under admin → Payment methods.
        </p>
      )}
      <div>
        <Label>Reference / transaction ID</Label>
        <Input value={txId} onChange={(e) => setTxId(e.target.value)} />
      </div>
      <Button
        className="w-full" disabled={!amount || !txId.trim()}
        onClick={() => onAdd({
          payment_method: "raast", amount,
          raast_transaction_id: txId.trim(),
          raast_iban: config.raast_iban || undefined,
        })}
      >
        Add tender
      </Button>
    </div>
  );
}

export function BankTransferSubFlow({ remaining, onAdd, config }: Props) {
  const [amount, setAmount] = useState(remaining.toStorageString());
  const [bank, setBank] = useState(PK_BANKS[0]);
  const [last4, setLast4] = useState("");
  const [ref, setRef] = useState("");

  return (
    <div className="space-y-3">
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      {config.bank_account_iban && (
        <div className="rounded-md border bg-muted/30 p-3 text-xs">
          <div>Receiver: <strong>{config.bank_account_name}</strong></div>
          <div className="font-mono">{config.bank_account_iban}</div>
          <div>{config.bank_account_bank}</div>
        </div>
      )}
      <div>
        <Label>Customer's bank</Label>
        <Select value={bank} onChange={(e) => setBank(e.target.value)}>
          {PK_BANKS.map((b) => <option key={b} value={b}>{b}</option>)}
        </Select>
      </div>
      <div>
        <Label>Last 4 (optional)</Label>
        <NumberInput
          mode="integer" maxLength={4}
          value={last4} onChange={setLast4}
          aria-label="Bank account last 4 digits"
        />
      </div>
      <div>
        <Label>Reference number</Label>
        <Input value={ref} onChange={(e) => setRef(e.target.value)} />
      </div>
      <Button
        className="w-full" disabled={!amount || !bank || !ref.trim()}
        onClick={() => onAdd({
          payment_method: "bank_transfer", amount,
          bank_name: bank, bank_account_last4: last4 || undefined,
          bank_reference: ref.trim(),
        })}
      >
        Add tender
      </Button>
    </div>
  );
}

export function StoreCreditSubFlow({
  remaining, onAdd, hasCustomer, storeCredit,
}: Props) {
  const cap = storeCredit.lt(remaining) ? storeCredit : remaining;
  const [amount, setAmount] = useState(cap.toStorageString());
  const tend = amount ? Money.fromStr(amount) : Money.zero();

  if (!hasCustomer) {
    return (
      <p className="rounded bg-warning-soft p-2 text-xs text-warning-soft-foreground">
        Store credit requires a registered customer on the sale. Pick a
        customer from the cart pane first.
      </p>
    );
  }
  if (storeCredit.isZero() || storeCredit.isNegative()) {
    return (
      <p className="rounded bg-warning-soft p-2 text-xs text-warning-soft-foreground">
        This customer has no store credit available.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm">
        Available store credit: <span className="font-mono">Rs {storeCredit.display()}</span>
      </p>
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      <Button
        className="w-full"
        disabled={!amount || tend.gt(storeCredit) || tend.isZero()}
        onClick={() => onAdd({
          payment_method: "store_credit", amount,
        })}
      >
        Apply store credit
      </Button>
      {tend.gt(storeCredit) && (
        <p className="text-xs text-destructive">
          Cannot apply more than available store credit.
        </p>
      )}
    </div>
  );
}

export function ChequeSubFlow({ remaining, onAdd }: Props) {
  const [amount, setAmount] = useState(remaining.toStorageString());
  const [number, setNumber] = useState("");
  const [bank, setBank] = useState(PK_BANKS[0]);
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));

  return (
    <div className="space-y-3">
      <AmountField amount={amount} setAmount={setAmount} remaining={remaining} />
      <div>
        <Label>Cheque number</Label>
        <Input value={number} onChange={(e) => setNumber(e.target.value)} />
      </div>
      <div>
        <Label>Bank</Label>
        <Select value={bank} onChange={(e) => setBank(e.target.value)}>
          {PK_BANKS.map((b) => <option key={b} value={b}>{b}</option>)}
        </Select>
      </div>
      <div>
        <Label>Cheque date</Label>
        <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </div>
      <Button
        className="w-full" disabled={!amount || !number.trim() || !date}
        onClick={() => onAdd({
          payment_method: "cheque", amount,
          cheque_number: number.trim(), bank_name: bank, cheque_date: date,
        })}
      >
        Add cheque
      </Button>
      <p className="text-xs text-muted-foreground">
        Cheque records as 'pending'. Mark cleared/bounced from admin →
        Cheques later.
      </p>
    </div>
  );
}
