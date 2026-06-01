export type Province =
  | "PUNJAB" | "SINDH" | "KP" | "BALOCHISTAN" | "ICT" | "GB" | "AJK";

export interface Branch {
  id: string;
  name: string;
  code: string;
  address: string;
  city: string;
  province: Province;
  phone: string | null;
  is_active: boolean;
  is_default: boolean;
  /** FBR-issued POS ID for this outlet (e.g. "194444"). Stored for
   *  traceability/receipts; NOT sent in the PRAL invoice payload. */
  fbr_pos_id: string | null;
  /** FBR-issued POS verification Code (e.g. "3364862B"). */
  fbr_pos_code: string | null;
  receipt_header: string | null;
  receipt_footer: string | null;
  created_at: string;
  updated_at: string;
}

export interface Terminal {
  id: string;
  branch: string;
  name: string;
  /** Stable per-branch ordinal (1, 2, 3 …); drives the …-T{index}-… segment
   *  of invoice numbers so terminals in one branch never collide. */
  terminal_index: number | null;
  device_fingerprint: string;
  os_version: string | null;
  app_version: string | null;
  printer_config: Record<string, unknown>;
  scanner_config: Record<string, unknown>;
  drawer_config: Record<string, unknown>;
  customer_display_enabled: boolean;
  is_active: boolean;
  last_seen_at: string | null;
  last_synced_at: string | null;
}
