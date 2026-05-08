export interface StockLevel {
  id: string;
  product: string;
  variant: string | null;
  branch: string;
  quantity: string;
  reserved_quantity: string;
  reorder_level: string | null;
  last_counted_at: string | null;
  updated_at: string;
}

export type MovementType =
  | "sale" | "return" | "purchase"
  | "transfer_in" | "transfer_out"
  | "adjustment_in" | "adjustment_out"
  | "damage" | "expiry" | "opening_balance";

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
