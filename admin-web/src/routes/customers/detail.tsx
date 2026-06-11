import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { extractApiErrorMessage } from "@/lib/api";
import {
  useCustomer,
  useCustomerLedger,
  useUpsertCustomer,
  type AdminCustomer,
} from "@/lib/queries";

function formatRs(amount: string): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return amount;
  return `Rs. ${n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const EMPTY: Partial<AdminCustomer> = {
  name: "",
  phone: "",
  email: "",
  cnic: "",
  ntn: "",
  registration_type: "unregistered",
  province: "",
  address: "",
  credit_limit: "0",
  notes: "",
  is_active: true,
};

export default function CustomerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = !id || id === "new";

  const { data: existing } = useCustomer(isNew ? undefined : id);
  const ledger = useCustomerLedger(isNew ? undefined : id);
  const upsert = useUpsertCustomer();

  const [form, setForm] = useState<Partial<AdminCustomer>>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (existing) setForm(existing);
  }, [existing]);

  function field<K extends keyof AdminCustomer>(key: K) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function save() {
    setError(null);
    // Guard: registration_type must be one of "registered" / "unregistered".
    // Empty / null fails DRF validation with a generic "not a valid choice"
    // 400 — default to unregistered when the field is blank.
    const regType: "registered" | "unregistered" =
      form.registration_type === "registered" ? "registered" : "unregistered";
    try {
      await upsert.mutateAsync({
        ...(isNew ? {} : { id }),
        name: form.name?.trim() ?? "",
        phone: form.phone || null,
        email: form.email || null,
        cnic: form.cnic || null,
        ntn: form.ntn || null,
        registration_type: regType,
        province: form.province || null,
        address: form.address ?? "",
        credit_limit: form.credit_limit ?? "0",
        notes: form.notes ?? "",
      });
      // Post-create: return to the customers list. Same UX principle
      // as the Tenant admin — the operator filled a complete form in
      // one shot; drop them back to the list with the new row in it
      // rather than the edit page (which would otherwise re-show the
      // same form and feel like nothing happened).
      if (isNew) navigate("/customers", { replace: true });
    } catch (e) {
      // DRF returns field-level errors as `{ field: ["message", ...] }`.
      // ApiError.data carries that body; surface the first useful message
      // so the operator sees the actual reason (e.g. "ntn: already
      // exists") instead of a generic "Save failed."
      setError(extractApiErrorMessage(e));
    }
  }

  return (
    <div className="space-y-4">
      <Link to="/customers" className="text-sm text-muted-foreground hover:underline">
        ← Customers
      </Link>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-baseline sm:justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">
          {isNew ? "New customer" : form.name || "Customer"}
        </h1>
        {!isNew && existing && (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span>
              Balance:{" "}
              <span className="font-mono">{formatRs(existing.current_balance)}</span>
            </span>
            <span>
              Store credit:{" "}
              <span className="font-mono">{formatRs(existing.store_credit)}</span>
            </span>
            <Badge variant={existing.is_active ? "default" : "secondary"}>
              {existing.is_active ? "active" : "inactive"}
            </Badge>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Profile</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <Label>Name</Label>
              <Input value={form.name ?? ""} onChange={field("name")} />
            </div>
            <div>
              <Label>Phone</Label>
              <Input value={form.phone ?? ""} onChange={field("phone")} placeholder="03001234567" />
            </div>
            <div>
              <Label>Email</Label>
              <Input value={form.email ?? ""} onChange={field("email")} />
            </div>
            <div>
              <Label>CNIC</Label>
              <Input value={form.cnic ?? ""} onChange={field("cnic")} placeholder="35202-1234567-1" />
            </div>
            <div>
              <Label>NTN</Label>
              <Input value={form.ntn ?? ""} onChange={field("ntn")} />
            </div>
            <div>
              <Label>Registration</Label>
              <Select value={form.registration_type ?? "unregistered"} onChange={field("registration_type")}>
                <option value="unregistered">Unregistered</option>
                <option value="registered">Registered</option>
              </Select>
            </div>
            <div>
              <Label>Province</Label>
              <Select value={form.province ?? ""} onChange={field("province")}>
                <option value="">—</option>
                <option value="PUNJAB">Punjab</option>
                <option value="SINDH">Sindh</option>
                <option value="KPK">Khyber Pakhtunkhwa</option>
                <option value="BALOCHISTAN">Balochistan</option>
                <option value="GB">Gilgit-Baltistan</option>
                <option value="AJK">Azad Jammu & Kashmir</option>
                <option value="ICT">Islamabad Capital Territory</option>
              </Select>
            </div>
            <div>
              <Label>Credit limit (Rs)</Label>
              <Input value={form.credit_limit ?? "0"} onChange={field("credit_limit")} />
            </div>
            <div className="md:col-span-2">
              <Label>Address</Label>
              <textarea
                rows={2}
                value={form.address ?? ""}
                onChange={field("address")}
                className="w-full rounded-md border bg-background px-2 py-1 text-sm"
              />
            </div>
            <div className="md:col-span-2">
              <Label>Notes</Label>
              <textarea
                rows={2}
                value={form.notes ?? ""}
                onChange={field("notes")}
                className="w-full rounded-md border bg-background px-2 py-1 text-sm"
              />
            </div>
            {error && <p className="md:col-span-2 text-sm text-destructive">{error}</p>}
            <div className="md:col-span-2 flex justify-end gap-2">
              <Button variant="outline" onClick={() => navigate("/customers")}>
                Cancel
              </Button>
              <Button onClick={save} disabled={upsert.isPending || !form.name?.trim()}>
                {upsert.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Ledger</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {isNew ? (
              <p className="p-4 text-xs text-muted-foreground">Save first to see ledger.</p>
            ) : !ledger.data || ledger.data.results.length === 0 ? (
              <p className="p-4 text-xs text-muted-foreground">No transactions yet.</p>
            ) : (
              <ul className="max-h-96 divide-y overflow-y-auto">
                {ledger.data.results.map((row) => (
                  <li key={row.id} className="px-3 py-2 text-xs">
                    <div className="flex justify-between">
                      <span className="font-medium capitalize">
                        {row.transaction_type.replace(/_/g, " ")}
                      </span>
                      <span className="font-mono">
                        {Number(row.debit) > 0
                          ? `+${formatRs(row.debit)}`
                          : `-${formatRs(row.credit)}`}
                      </span>
                    </div>
                    <div className="flex justify-between text-muted-foreground">
                      <span>{row.created_at.slice(0, 16).replace("T", " ")}</span>
                      <span>Bal: {formatRs(row.running_balance)}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
