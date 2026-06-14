export interface StockLevel {
  id: string;
  product: string;
  variant: string | null;
  branch: string;
  /** Warehouse (Digital-Invoicing) the stock sits in; null for branch-keyed
   *  (POS / legacy) stock. */
  warehouse: string | null;
  warehouse_name?: string | null;
  quantity: string;
  reserved_quantity: string;
  reorder_level: string | null;
  last_counted_at: string | null;
  updated_at: string;
}

/** A warehouse (godown) under a branch — Digital-Invoicing stock location. */
export interface Warehouse {
  id: string;
  branch: string;
  branch_name: string;
  name: string;
  code: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type MovementType =
  | "sale" | "return" | "purchase"
  | "transfer_in" | "transfer_out"
  | "adjustment_in" | "adjustment_out"
  | "damage" | "expiry" | "opening_balance";

/** A stock batch (pharmacy / date-sensitive goods). Money values are 4dp
 *  decimal strings; quantities are decimal strings. */
export interface ProductBatch {
  id: string;
  product: string;
  product_name: string;
  batch_number: string;
  manufactured_date: string | null;
  expiry_date: string | null;
  cost_price: string | null;
  sale_price: string | null;
  initial_quantity: string;
  current_quantity: string;
  branch: string | null;
  branch_name: string | null;
  created_at: string;
}

export interface StockMovement {
  id: string;
  product: string;
  variant: string | null;
  batch: string | null;
  branch: string;
  movement_type: MovementType;
  quantity: string;
  unit_cost: string | null;
  reference_type: string | null;
  reference_id: string | null;
  reason: string;
  performed_by: string | null;
  created_at: string;
}

export type TransferStatus = "draft" | "dispatched" | "received" | "cancelled";

export interface StockTransferItem {
  id: string;
  transfer: string;
  product: string;
  variant: string | null;
  quantity_dispatched: string;
  quantity_received: string | null;
  variance: string | null;
}

export interface StockTransfer {
  id: string;
  transfer_number: string;
  from_branch: string;
  to_branch: string;
  status: TransferStatus;
  dispatched_at: string | null;
  dispatched_by: string | null;
  received_at: string | null;
  received_by: string | null;
  notes: string;
  items: StockTransferItem[];
  created_at: string;
  updated_at: string;
}

export type AuditStatus = "in_progress" | "finalized" | "cancelled";

export interface StockAuditItem {
  id: string;
  audit: string;
  product: string;
  variant: string | null;
  expected_quantity: string;
  counted_quantity: string;
  variance: string;
  variance_reason: string;
}

export interface StockAudit {
  id: string;
  branch: string;
  audit_number: string;
  status: AuditStatus;
  started_at: string;
  finalized_at: string | null;
  performed_by: string | null;
  notes: string;
  items: StockAuditItem[];
  created_at: string;
  updated_at: string;
}
