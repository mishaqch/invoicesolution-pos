/**
 * Single source of truth for invoice-status presentation.
 *
 * The backend `apps/sales/models.py:INVOICE_STATUSES` defines 10
 * possible values. Picking colors for them is a UX decision, so we
 * centralize it here — that way the badge in the list, the chip on
 * the detail page, and any future surface (PDF export, receipts,
 * notifications) read the same and stay consistent.
 *
 * Mapping:
 *
 *   valid / finalized                          → success (green)
 *     - happy terminal states (FBR-validated, locked into a return)
 *
 *   submitted                                  → info (blue)
 *     - in flight; PRAL accepted the payload but final validation
 *       hasn't completed yet
 *
 *   pending_sync                               → warning (amber)
 *     - not yet on PRAL, operator may want to retry
 *
 *   failed                                     → destructive (red)
 *     - hard error; needs human attention
 *
 *   cancelled                                  → muted (grey)
 *     - terminal but neutral; the invoice is dead but not "wrong"
 *
 *   edited                                     → info (blue)
 *     - item-level edits within the 72h window; still valid
 *
 *   partially_edited
 *   partially_cancelled
 *   partially_edited_and_cancelled             → warning (amber)
 *     - mixed states; reviewer should look at line-level flags
 */

import type { BadgeProps } from "@/components/ui/badge";

export type InvoiceStatus =
  | "pending_sync"
  | "submitted"
  | "valid"
  | "failed"
  | "edited"
  | "partially_edited"
  | "cancelled"
  | "partially_cancelled"
  | "partially_edited_and_cancelled"
  | "finalized";

type Variant = NonNullable<BadgeProps["variant"]>;

const VARIANT_BY_STATUS: Record<InvoiceStatus, Variant> = {
  valid: "success",
  finalized: "success",
  submitted: "info",
  edited: "info",
  pending_sync: "warning",
  partially_edited: "warning",
  partially_cancelled: "warning",
  partially_edited_and_cancelled: "warning",
  failed: "destructive",
  cancelled: "muted",
};

const LABEL_BY_STATUS: Record<InvoiceStatus, string> = {
  // "Draft" is the operator-friendly label for `pending_sync` —
  // means the invoice is saved locally but has not been sent to FBR
  // yet. Manual invoices stay in this state until the operator
  // explicitly clicks "Submit to FBR" on the detail page. POS-terminal
  // sales pass through it briefly while the async sync queue runs.
  pending_sync: "Draft",
  submitted: "Submitted",
  valid: "Validated",
  failed: "Failed",
  edited: "Edited",
  partially_edited: "Partially edited",
  cancelled: "Cancelled",
  partially_cancelled: "Partially cancelled",
  partially_edited_and_cancelled: "Edited & cancelled",
  finalized: "Finalized",
};

// Short human-readable hint shown in `title` tooltips. Keeps the badge
// label terse while still letting operators discover what the state
// means by hovering.
const HINT_BY_STATUS: Record<InvoiceStatus, string> = {
  pending_sync: "Saved locally but not yet submitted to FBR. Open the invoice and click 'Submit to FBR' to issue the FBR Invoice Number.",
  submitted: "Sent to FBR; awaiting final validation.",
  valid: "Validated by FBR. Has an FBR invoice number.",
  failed: "FBR rejected this submission. Fix the data and resubmit.",
  edited: "Item-level edit applied within the 72-hour window.",
  partially_edited: "Some line items have been edited.",
  cancelled: "Invoice has been cancelled. No longer counts toward sales.",
  partially_cancelled: "Some line items have been cancelled.",
  partially_edited_and_cancelled:
    "Some items edited, others cancelled.",
  finalized: "Locked into a submitted sales-tax return; immutable.",
};

export function invoiceStatusVariant(status: string): Variant {
  return VARIANT_BY_STATUS[status as InvoiceStatus] ?? "outline";
}

export function invoiceStatusLabel(status: string): string {
  if (status in LABEL_BY_STATUS) {
    return LABEL_BY_STATUS[status as InvoiceStatus];
  }
  // Fallback for any new server-side status we haven't catalogued yet:
  // turn snake_case into Title Case so it at least reads.
  return status.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

export function invoiceStatusHint(status: string): string | undefined {
  return HINT_BY_STATUS[status as InvoiceStatus];
}
