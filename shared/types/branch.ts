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
  fbr_pos_id: string | null;
  receipt_header: string | null;
  receipt_footer: string | null;
  created_at: string;
  updated_at: string;
}

export interface Terminal {
  id: string;
  branch: string;
  name: string;
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
