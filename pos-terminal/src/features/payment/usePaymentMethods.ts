/**
 * Fetches the tenant's payment-method config once at the payment screen mount.
 * Returns enabled methods + per-method config (QR URLs, IBANs, etc.).
 */

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";

export interface PaymentMethodConfig {
  enabled_payment_methods: string[];
  easypaisa_qr_url: string;
  jazzcash_qr_url: string;
  raast_qr_url: string;
  raast_iban: string;
  bank_account_name: string;
  bank_account_iban: string;
  bank_account_bank: string;
}

export function usePaymentMethods() {
  const [config, setConfig] = useState<PaymentMethodConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const c = await api<PaymentMethodConfig>("/payments/methods/");
        if (!cancelled) setConfig(c);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? `API ${err.status}` : "Failed to load methods.");
          // Fall back to cash-only so the cashier can still complete sales offline.
          setConfig({
            enabled_payment_methods: ["cash"],
            easypaisa_qr_url: "", jazzcash_qr_url: "",
            raast_qr_url: "", raast_iban: "",
            bank_account_name: "", bank_account_iban: "", bank_account_bank: "",
          });
        }
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return { config, error };
}
