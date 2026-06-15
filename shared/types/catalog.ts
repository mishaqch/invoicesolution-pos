export interface UnitOfMeasure {
  code: string;
  name_en: string;
  name_ur: string;
  is_decimal_quantity: boolean;
  /** Exact unit string FBR/PRAL accepts for this code (e.g. "Numbers, pieces,
   *  units"). Several local codes can share one fbr_uom; the product form
   *  groups the dropdown by this. */
  fbr_uom?: string;
  /** Friendly DISPLAY label for the fbr_uom (e.g. "Kilogram" for "KG").
   *  Presentation only — submission still uses fbr_uom. */
  fbr_uom_label?: string;
}

export interface HsCode {
  code: string;
  description: string;
  default_tax_rate: string | null;
  uom_default: string | null;
  parent_code: string | null;
}

export interface TaxRate {
  id: string;
  name: string;
  rate: string;
  is_compound: boolean;
  applies_to: "goods" | "services" | "both";
  is_default: boolean;
}

export interface Category {
  id: string;
  parent: string | null;
  name: string;
  name_ur: string;
  slug: string;
  display_order: number;
  color: string | null;
  icon: string | null;
  is_active: boolean;
}

export interface Product {
  id: string;
  category: string | null;
  name: string;
  name_ur: string;
  description: string;
  sku: string;
  barcode: string | null;
  hs_code: string | null;
  uom: string;
  tax_rate: string | null;
  is_taxable: boolean;
  cost_price?: string;            // present in admin payload only
  sale_price: string;
  retail_price: string | null;
  min_sale_price: string | null;
  max_discount_pct: string | null;
  // Pakistan 3rd-Schedule flag. When true, FBR submission uses
  // retail_price * qty as the taxable base + saleType="3rd Schedule
  // Goods" (instead of sale_price-based math). Required by PRAL for
  // sugar / drinks / biscuits / cigarettes / mobile phones etc.
  is_third_schedule: boolean;
  reorder_level: string | null;
  reorder_quantity: string | null;
  is_serialized: boolean;
  is_batch_tracked: boolean;
  is_weighable: boolean;
  has_variants: boolean;
  image_url: string;
  is_active: boolean;
  created_at?: string;
  updated_at: string;
  deleted_at: string | null;
}

/** What the POS terminal receives from /api/catalog/sync/ — no cost_price. */
export type PosProduct = Omit<Product, "cost_price" | "description" | "is_serialized" | "is_batch_tracked" | "has_variants" | "reorder_level" | "reorder_quantity" | "created_at">;
