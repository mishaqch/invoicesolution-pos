import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  usePaymentSettings,
  useUpdatePaymentSettings,
  type PaymentSettings,
} from "@/lib/queries";

const ALL_METHODS: { code: string; label: string }[] = [
  { code: "cash", label: "Cash" },
  { code: "card_credit", label: "Card (credit)" },
  { code: "card_debit", label: "Card (debit)" },
  { code: "easypaisa", label: "EasyPaisa" },
  { code: "jazzcash", label: "JazzCash" },
  { code: "raast", label: "Raast" },
  { code: "bank_transfer", label: "Bank transfer" },
  { code: "store_credit", label: "Store credit" },
  { code: "cheque", label: "Cheque" },
];

export default function PaymentSettingsPage() {
  const { data } = usePaymentSettings();
  const update = useUpdatePaymentSettings();

  const [draft, setDraft] = useState<Partial<PaymentSettings>>({});
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data) setDraft(data);
  }, [data]);

  function toggleMethod(code: string, enabled: boolean) {
    const current = new Set(draft.enabled_payment_methods ?? []);
    if (enabled) current.add(code);
    else current.delete(code);
    setDraft({ ...draft, enabled_payment_methods: Array.from(current) });
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await update.mutateAsync(draft);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    }
  }

  if (!data) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  const enabled = new Set(draft.enabled_payment_methods ?? []);

  return (
    <form onSubmit={save} className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight">Payment methods</h1>
      <p className="text-sm text-muted-foreground">
        Enable the methods this tenant accepts and configure per-method details.
        QR codes are uploaded by the tenant — paste an image URL (Backblaze upload UI lands in Phase 8).
      </p>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Enabled methods</CardTitle>
          <CardDescription>
            Cashiers only see methods enabled here on the POS payment screen.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            {ALL_METHODS.map((m) => (
              <label key={m.code} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={enabled.has(m.code)}
                  onChange={(e) => toggleMethod(m.code, e.target.checked)}
                />
                {m.label}
              </label>
            ))}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-sm">EasyPaisa</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Field label="Merchant ID">
              <Input
                value={draft.easypaisa_merchant_id ?? ""}
                onChange={(e) => setDraft({ ...draft, easypaisa_merchant_id: e.target.value })}
              />
            </Field>
            <Field label="QR image URL">
              <Input
                value={draft.easypaisa_qr_url ?? ""}
                onChange={(e) => setDraft({ ...draft, easypaisa_qr_url: e.target.value })}
                placeholder="https://…/easypaisa-qr.png"
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-sm">JazzCash</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Field label="Merchant ID">
              <Input
                value={draft.jazzcash_merchant_id ?? ""}
                onChange={(e) => setDraft({ ...draft, jazzcash_merchant_id: e.target.value })}
              />
            </Field>
            <Field label="QR image URL">
              <Input
                value={draft.jazzcash_qr_url ?? ""}
                onChange={(e) => setDraft({ ...draft, jazzcash_qr_url: e.target.value })}
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-sm">Raast</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Field label="IBAN (receiver)">
              <Input
                value={draft.raast_iban ?? ""}
                onChange={(e) => setDraft({ ...draft, raast_iban: e.target.value })}
                placeholder="PK36SCBL0000001123456702"
              />
            </Field>
            <Field label="QR image URL">
              <Input
                value={draft.raast_qr_url ?? ""}
                onChange={(e) => setDraft({ ...draft, raast_qr_url: e.target.value })}
              />
            </Field>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-sm">Bank account (for bank transfer)</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Field label="Bank name">
              <Input
                value={draft.bank_account_bank ?? ""}
                onChange={(e) => setDraft({ ...draft, bank_account_bank: e.target.value })}
                placeholder="HBL / MCB / UBL …"
              />
            </Field>
            <Field label="Account name">
              <Input
                value={draft.bank_account_name ?? ""}
                onChange={(e) => setDraft({ ...draft, bank_account_name: e.target.value })}
              />
            </Field>
            <Field label="IBAN">
              <Input
                value={draft.bank_account_iban ?? ""}
                onChange={(e) => setDraft({ ...draft, bank_account_iban: e.target.value })}
              />
            </Field>
          </CardContent>
        </Card>
      </div>

      <div className="flex items-center gap-3">
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? "Saving…" : "Save"}
        </Button>
        {saved && <span className="text-sm text-green-700">Saved.</span>}
        {error && <span className="text-sm text-destructive">{error}</span>}
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
