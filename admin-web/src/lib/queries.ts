import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  Branch, Category, HsCode, PosProduct, Product,
  StockAudit, StockLevel, StockMovement, StockTransfer,
  TaxRate, UnitOfMeasure,
} from "@pos/shared/types";

import { useModules, type ModuleKey } from "@/features/modules/hooks";
import { api } from "./api";

/**
 * Returns true while `modules` is loading (so the query fires once),
 * and after it resolves, returns whether the module is in the enabled
 * set. Used to gate every data hook that maps to a tenant module —
 * keeps the gated 403s from spamming the console when super-admin
 * has turned the module off for this tenant.
 */
function useModuleEnabled(key: ModuleKey): boolean {
  // While useModules() is still loading we deliberately return FALSE
  // (not the optimistic TRUE you'd expect for "don't flicker the UI").
  // Reason: data hooks like useBranches/useTerminals/useCustomers
  // pass this value as React Query's `enabled` flag. Returning true
  // during loading fires the gated GET, which 403s for tenants
  // whose super-admin has the module turned off — spamming the
  // console with errors for an outcome we KNOW is "module off".
  // Better to wait the ~30-50ms for /me/modules/ to resolve and only
  // then issue the gated call, even at the cost of a tiny render
  // delay. Once `data` arrives, we evaluate against `enabled` for
  // real and never make a wrong request.
  const { data } = useModules();
  return data ? data.enabled.includes(key) : false;
}

interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ----- Catalog -----
export function useUoms() {
  return useQuery({
    queryKey: ["uoms"],
    queryFn: () => api<UnitOfMeasure[]>("/catalog/uoms/"),
    staleTime: 1000 * 60 * 60,
  });
}

export function useTaxRates() {
  return useQuery({
    queryKey: ["tax-rates"],
    queryFn: () => api<Page<TaxRate>>("/catalog/tax-rates/"),
  });
}

export function useCategories() {
  return useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Page<Category>>("/catalog/categories/?page_size=200"),
  });
}

export function useProducts(params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return useQuery({
    queryKey: ["products", params],
    queryFn: () => api<Page<Product>>(`/catalog/products/${query ? `?${query}` : ""}`),
  });
}

export function useProduct(id: string | undefined) {
  return useQuery({
    queryKey: ["product", id],
    queryFn: () => api<Product>(`/catalog/products/${id}/`),
    enabled: !!id,
  });
}

export function useHsCodes(query: string) {
  return useQuery({
    queryKey: ["hs-codes", query],
    queryFn: () =>
      api<Page<HsCode>>(`/catalog/hs-codes/${query ? `?search=${encodeURIComponent(query)}` : ""}`),
    placeholderData: (prev) => prev,
  });
}

export interface HsCodesMeta {
  count: number;
  last_synced_at: string | null;
}

export function useHsCodesMeta() {
  return useQuery({
    queryKey: ["hs-codes", "meta"],
    queryFn: () => api<HsCodesMeta>("/catalog/hs-codes/meta/"),
    // Catalog only changes when someone runs the sync command, so we
    // can be relaxed about freshness here.
    staleTime: 5 * 60 * 1000,
  });
}

export function useCreateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Product>) =>
      api<Product>("/catalog/products/", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
  });
}

export function useUpdateProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Product> & { id: string }) =>
      api<Product>(`/catalog/products/${id}/`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["product", data.id] });
    },
  });
}

export function useDeleteProduct() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<void>(`/catalog/products/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["products"] }),
  });
}

// ----- Branches -----
//
// Gated on the `branches` module. Tenants without the module get an
// empty result instead of a 403 — callers (filter dropdowns, branch
// pickers) render a sensible "no branches available" state without us
// having to thread the module check into every page.
export function useBranches() {
  const enabled = useModuleEnabled("branches");
  return useQuery({
    queryKey: ["branches"],
    queryFn: () => api<Page<Branch>>("/branches/"),
    enabled,
    initialData: enabled
      ? undefined
      : ({ count: 0, next: null, previous: null, results: [] } as Page<Branch>),
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useCreateBranch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Branch>) =>
      api<Branch>("/branches/", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["branches"] }),
  });
}

export function useUpdateBranch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<Branch> & { id: string }) =>
      api<Branch>(`/branches/${id}/`, { method: "PATCH", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["branches"] }),
  });
}

// ----- Terminal pairing mutations (AdminTerminal type lives further below) -----
export function useCreateTerminal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { branch: string; name: string }) =>
      api<{ id: string }>("/terminals/", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["terminals"] }),
  });
}

export function useIssuePairingCode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<{ pairing_code: string; pairing_code_expires_at: string }>(
        `/terminals/${id}/issue-code/`, { method: "POST" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["terminals"] }),
  });
}

export function useDeactivateTerminal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<void>(`/terminals/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["terminals"] }),
  });
}

// ----- Inventory -----
export function useStockLevels(params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return useQuery({
    queryKey: ["stock-levels", params],
    queryFn: () => api<Page<StockLevel>>(`/inventory/stock-levels/${query ? `?${query}` : ""}`),
  });
}

export function useStockMovements(params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return useQuery({
    queryKey: ["movements", params],
    queryFn: () => api<Page<StockMovement>>(`/inventory/movements/${query ? `?${query}` : ""}`),
  });
}

export function usePostAdjustment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      branch: string; product: string; variant?: string | null;
      quantity: string; movement_type: string; reason: string;
    }) =>
      api<StockMovement>("/inventory/adjustments/", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stock-levels"] });
      qc.invalidateQueries({ queryKey: ["movements"] });
    },
  });
}

export function useTransfers() {
  return useQuery({
    queryKey: ["transfers"],
    queryFn: () => api<Page<StockTransfer>>("/inventory/transfers/"),
  });
}

export function useAudits() {
  return useQuery({
    queryKey: ["audits"],
    queryFn: () => api<Page<StockAudit>>("/inventory/audits/"),
  });
}

export type { Branch, Category, HsCode, PosProduct, Product, TaxRate, UnitOfMeasure };

// ---------- Sales (Phase 2) ----------

export interface InvoiceLine {
  id: string;
  line_number: number;
  product: string;
  product_name: string;
  product_sku: string;
  // PRAL HS code snapshotted on this line at sale time. Read by the
  // FBR builder and shown on the invoice detail line items table.
  hs_code: string | null;
  uom_code: string;
  quantity: string;
  unit_price: string;
  discount_pct: string;
  discount_amount: string;
  tax_rate: string;
  tax_amount: string;
  line_total: string;
  is_edited: boolean;
  is_cancelled: boolean;
}

export interface InvoicePayment {
  id: string;
  payment_method: string;
  amount: string;
  status: string;
  card_last4: string | null;
  created_at: string;
}

export interface AdminInvoice {
  id: string;
  branch: string;
  // Branch's FBR POS ID. Non-null => POS/SDC tenant (show the SDC fiscalize
  // button, hide the DI-API Validate/Submit buttons).
  branch_fbr_pos_id: string | null;
  terminal: string;
  cashier: string;
  customer: string | null;
  local_invoice_number: string;
  fbr_invoice_number: string | null;
  fbr_qr_payload: string | null;
  invoice_type: string;
  invoice_date: string;
  reference_invoice: string | null;
  buyer_name: string | null;
  buyer_phone: string | null;
  buyer_ntn_cnic: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  change_given: string;
  status: string;
  edit_deadline_at: string | null;
  is_held: boolean;
  held_label: string | null;
  notes: string | null;
  items: InvoiceLine[];
  payments: InvoicePayment[];
  // Public, HMAC-signed download URL for the FBR-validated PDF.
  // Returned by the backend only when the invoice has been validated
  // by FBR (and therefore has an FBR invoice number). Used by
  // SendToBuyer for WhatsApp + email — pasting this URL into a
  // message lets the buyer download the PDF without signing in.
  // Token TTL: 7 days (see apps/sales/services/share_links.py).
  share_url: string | null;
  created_at: string;
  updated_at: string;
}

interface InvoiceFilters {
  branch?: string;
  status?: string;
  cashier?: string;
  customer?: string;
  from?: string;
  to?: string;
  held?: string;
  q?: string;
}

export function useInvoices(filters: InvoiceFilters = {}) {
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) if (v) cleaned[k] = v;
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["invoices", filters],
    queryFn: () =>
      api<{ count: number; results: AdminInvoice[] }>(
        `/sales/invoices/${query ? `?${query}` : ""}`,
      ),
  });
}

export interface InvoiceSummary {
  by_status: Record<string, { count: number; revenue: string }>;
  total_count: number;
  total_revenue: string;
}

export type TimeseriesInterval = "day" | "month" | "quarter" | "year";
export type TimeseriesInvoiceType = "sale" | "debit_note" | "credit_note";

export interface TimeseriesBucket {
  label: string;
  count: number;
  revenue: string;
}

export interface InvoiceTimeseries {
  interval: TimeseriesInterval;
  invoice_type: TimeseriesInvoiceType;
  buckets: TimeseriesBucket[];
}

export function useInvoiceTimeseries(
  interval: TimeseriesInterval = "day",
  invoiceType: TimeseriesInvoiceType = "sale",
  filters: Pick<InvoiceFilters, "branch" | "from" | "to"> = {},
) {
  const cleaned: Record<string, string> = {
    interval, invoice_type: invoiceType,
  };
  for (const k of ["branch", "from", "to"] as const) {
    if (filters[k]) cleaned[k] = filters[k]!;
  }
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["invoices-timeseries", cleaned],
    queryFn: () =>
      api<InvoiceTimeseries>(`/sales/invoices/timeseries/?${query}`),
  });
}

export function useInvoiceSummary(filters: InvoiceFilters = {}) {
  const cleaned: Record<string, string> = {};
  // Summary respects branch + date filters but ignores status/q (the KPI
  // tiles are themselves the status filter, and search is for the table).
  for (const k of ["branch", "from", "to"] as const) {
    if (filters[k]) cleaned[k] = filters[k]!;
  }
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["invoices-summary", cleaned],
    queryFn: () =>
      api<InvoiceSummary>(
        `/sales/invoices/summary/${query ? `?${query}` : ""}`,
      ),
  });
}

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: ["invoice", id],
    queryFn: () => api<AdminInvoice>(`/sales/invoices/${id}/`),
    enabled: !!id,
  });
}

export function useCancelInvoice() {
  const qc = useQueryClient();
  // PRAL DI manual v1.6 §"Conditions for Invoice Cancellation":
  // cancelling an FBR-validated invoice must (a) consume the tenant's
  // 10% monthly cancel-budget and (b) tell PRAL via the cancelinvoice
  // endpoint so the invoice is amended on FBR's side too. The
  // FBR-aware endpoint at /api/fbr/invoices/<id>/cancel/ does both.
  //
  // The legacy /api/sales/invoices/<id>/cancel/ endpoint is now a
  // superuser-only force-cancel escape hatch — it intentionally
  // bypasses the budget + PRAL call and should not be used from the
  // tenant admin's standard cancel flow.
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api<{ id: string; status: string }>(
        `/fbr/invoices/${id}/cancel/`,
        { method: "POST", body: JSON.stringify({ reason }) },
      ),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoices-summary"] });
      qc.invalidateQueries({ queryKey: ["invoice", data.id] });
      // Cancel budget is consumed by this call — refresh the budget
      // tile too so the tenant sees the remaining amount drop.
      qc.invalidateQueries({ queryKey: ["fbr-cancel-budget"] });
    },
  });
}

export interface EditItemInput {
  invoice_id: string;
  item_id: string;
  reason: string;
  quantity?: string;
  unit_price?: string;
  tax_rate?: string;
}

export function useEditInvoiceItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: EditItemInput) => {
      const { invoice_id, item_id, ...body } = input;
      return api<AdminInvoice>(
        `/sales/invoices/${invoice_id}/items/${item_id}/edit/`,
        { method: "POST", body: JSON.stringify(body) },
      );
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoices-summary"] });
      qc.invalidateQueries({ queryKey: ["invoice", data.id] });
    },
  });
}

export function useResubmitInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<AdminInvoice>(`/sales/invoices/${id}/resubmit/`, { method: "POST" }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoices-summary"] });
      qc.invalidateQueries({ queryKey: ["invoice", data.id] });
    },
  });
}

export interface ValidateInvoiceResult {
  valid: boolean;
  response?: unknown;
  error?: string;
  error_code?: string | null;
  // When the backend got a transient PRAL failure (502 / non-JSON /
  // timeout), it now returns `kind: "transient"` so the UI can show
  // a "PRAL service flaky, try again" message instead of the
  // misleading "PRAL rejected the payload".
  kind?: "transient";
  detail?: string;
}

export function useValidateInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api<ValidateInvoiceResult>(
        `/sales/invoices/${id}/validate/`, { method: "POST" },
      ),
    onSuccess: (_data, id) => {
      // Validate creates an FbrSubmission row; refresh the log panel.
      qc.invalidateQueries({ queryKey: ["fbr-submissions"] });
      qc.invalidateQueries({ queryKey: ["invoice", id] });
    },
  });
}

export function useCancelInvoiceItem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ invoice_id, item_id, reason }: {
      invoice_id: string; item_id: string; reason: string;
    }) =>
      api<AdminInvoice>(`/sales/invoices/${invoice_id}/items/${item_id}/cancel/`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      }),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["invoices"] });
      qc.invalidateQueries({ queryKey: ["invoice", data.id] });
    },
  });
}

// ---------- Sync (Phase 3) ----------

export interface TerminalSyncStatus {
  terminal: string;
  pending: number;
  failed: number;
  last_processed_at: string | null;
  last_seen_at: string | null;
}

export interface SyncLogEntry {
  id: string;
  terminal: string;
  client_uuid: string;
  entity_type: string;
  entity_id: string | null;
  action: string;
  status: "received" | "processed" | "failed" | "duplicate";
  error_message: string | null;
  received_at: string;
  processed_at: string | null;
}

export function useSyncStatus(terminalId?: string) {
  // /sync/status/ is gated by the `terminals` module on the server.
  // DI tenants (no terminals) used to get a 403 every 5 seconds from
  // the layout-wide SyncBanner — terabytes of console noise over a
  // session. Skip the call entirely when the module is off.
  const enabled = useModuleEnabled("terminals");
  return useQuery({
    queryKey: ["sync-status", terminalId],
    queryFn: () =>
      api<{ results: TerminalSyncStatus[] }>(
        `/sync/status/${terminalId ? `?terminal_id=${terminalId}` : ""}`,
      ),
    enabled,
    initialData: enabled ? undefined : ({ results: [] } as { results: TerminalSyncStatus[] }),
    refetchInterval: enabled ? 5000 : false,
  });
}

export function useSyncLog(filters: { terminal_id?: string; status?: string } = {}) {
  const enabled = useModuleEnabled("terminals");
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) if (v) cleaned[k] = v;
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["sync-log", filters],
    queryFn: () =>
      api<{ count: number; results: SyncLogEntry[] }>(
        `/sync/log/${query ? `?${query}` : ""}`,
      ),
    enabled,
    initialData: enabled ? undefined : ({ count: 0, results: [] } as { count: number; results: SyncLogEntry[] }),
    refetchInterval: enabled ? 5000 : false,
  });
}

export function useRetrySyncRow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api(`/sync/log/${id}/retry/`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sync-log"] });
      qc.invalidateQueries({ queryKey: ["sync-status"] });
    },
  });
}

export interface AdminTerminal {
  id: string;
  branch: string;
  name: string;
  // Stable per-branch ordinal (1, 2, 3 …) — drives the …-T{index}-… segment of
  // invoice numbers so multiple terminals in one branch never collide.
  terminal_index: number | null;
  device_fingerprint: string;
  os_version: string | null;
  app_version: string | null;
  is_active: boolean;
  last_seen_at: string | null;
  last_synced_at: string | null;
  customer_display_enabled: boolean;
  // Device-pairing state (one-time code the cashier enters in invoiceSolution.exe).
  pairing_code: string | null;
  pairing_code_expires_at: string | null;
  paired_at: string | null;
  is_paired: boolean;
}

export function useTerminals() {
  const enabled = useModuleEnabled("terminals");
  return useQuery({
    queryKey: ["terminals"],
    queryFn: () => api<{ count: number; results: AdminTerminal[] }>("/terminals/"),
    enabled,
    initialData: enabled
      ? undefined
      : ({ count: 0, results: [] } as { count: number; results: AdminTerminal[] }),
    retry: false,
    refetchOnWindowFocus: false,
  });
}

// ---------- FBR (Phase 4) ----------

export interface FbrTokenInfo {
  id: string;
  environment: "sandbox" | "production";
  api_endpoint: string;
  is_active: boolean;
  has_token: boolean;
  // Masked preview of the configured token — e.g. "865acb97…b0a9".
  // null when no token is set. Used by the FBR setup wizard so the
  // operator can confirm which bearer is on file without seeing
  // the secret.
  token_preview: string | null;
  activated_at: string | null;
  expires_at: string | null;
}

export interface FbrAssignedScenario {
  code: string;
  description: string;
  // true = we have a payload-builder; false = listed in IRIS but our
  // platform can't run this scenario yet (UI shows "Not yet supported").
  builder_available: boolean;
}

export interface FbrStatus {
  tenant_id: string;
  environment: "sandbox" | "production" | "none";
  sandbox: FbrTokenInfo | null;
  production: FbrTokenInfo | null;
  last_successful_submission_at: string | null;
  // The full set of scenarios assigned to this tenant (from IRIS), including
  // codes for which we don't have a builder yet. UI iterates over this.
  assigned_scenarios: FbrAssignedScenario[];
  // Subset of assigned_scenarios with a working builder. Used internally
  // by the runner + the all-passed gate.
  eligible_scenarios: FbrAssignedScenario[];
  passed_scenarios: string[];
  all_scenarios_passed: boolean;
}

export function useFbrStatus() {
  return useQuery({
    queryKey: ["fbr-status"],
    queryFn: () => api<FbrStatus>("/fbr/status/"),
    refetchInterval: 30_000,
  });
}

// ----- FBR POS connection status (per branch) -----
//
// Mirrors the Connected/Disconnected view in the FBR portal. A branch is
// "connected" once it has had at least one invoice validated by FBR. The
// POS ID + Code are the FBR-issued registration identifiers stored on the
// branch (for traceability/receipts — they are NOT sent in the payload; the
// production token is what authenticates submissions).
export interface FbrPosBranch {
  branch_id: string;
  branch_name: string;
  branch_code: string;
  fbr_pos_id: string | null;
  fbr_pos_code: string | null;
  registered: boolean;
  connected: boolean;
  last_validated_at: string | null;
  // Per-branch POS token (POS model: each outlet has its own token).
  has_branch_token: boolean;
  branch_token_active: boolean;
}

export interface FbrPosStatus {
  tenant_id: string;
  token_present: boolean;
  token_environment: "production" | "sandbox" | "none";
  branches: FbrPosBranch[];
}

export function useFbrPosStatus() {
  return useQuery({
    queryKey: ["fbr-pos-status"],
    queryFn: () => api<FbrPosStatus>("/fbr/pos-status/"),
    refetchInterval: 30_000,
  });
}

// Set/update a single branch's FBR POS bearer token. POS registrations get a
// production token directly from FBR — no sandbox/scenario gate.
export function useSetBranchToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { branch_id: string; token: string; api_endpoint?: string }) =>
      api("/fbr/branch-token/", { method: "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fbr-pos-status"] });
      qc.invalidateQueries({ queryKey: ["branches"] });
    },
  });
}

export function useDeactivateBranchToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (branch_id: string) =>
      api(`/fbr/branch-token/?branch_id=${encodeURIComponent(branch_id)}`, {
        method: "DELETE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fbr-pos-status"] }),
  });
}

export interface FbrScenarioRow {
  id: string;
  scenario_code: string;
  scenario_description: string;
  // `not_implemented` = listed in IRIS but our platform doesn't ship
  // a payload-builder for this code yet; runner skipped it.
  status: "pending" | "submitting" | "success" | "failed" | "not_implemented";
  fbr_invoice_number: string | null;
  last_attempt_at: string | null;
  error_message: string | null;
  // The most recent request payload we sent to PRAL for this scenario,
  // and PRAL's reply. Both are full JSON blobs (null when no submission
  // attempt has been made). Powers the per-scenario "Show request /
  // response" diagnostic inspector.
  last_request_payload: unknown | null;
  last_response_payload: unknown | null;
}

export function useFbrScenarios() {
  return useQuery({
    queryKey: ["fbr-scenarios"],
    queryFn: () =>
      api<{ count: number; results: FbrScenarioRow[] }>("/fbr/scenarios/"),
    refetchInterval: 5_000,
  });
}

export function useRunScenarios() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<{ results: Record<string, string> }>("/fbr/scenarios/run-all/", {
        method: "POST",
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fbr-scenarios"] });
      qc.invalidateQueries({ queryKey: ["fbr-status"] });
    },
  });
}

// Run a single scenario by code. Used by the per-card "Run" button so
// the operator can iterate on a failing scenario without re-running
// the whole batch (which is slow + spammy in the FbrSubmission log).
//
// `payload` (optional): when provided, the backend sends THIS JSON to
// PRAL instead of regenerating from the builder. This is the
// "edit JSON on the card and click Send" path — lets operators
// iterate on PRAL feedback in-browser without redeploying code.
// One-off: the override is NOT persisted; the next plain Run uses
// the builder again.
export function useRunSingleScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { code: string; payload?: unknown }) =>
      api<{ status: string; scenario: FbrScenarioRow | null }>(
        `/fbr/scenarios/${args.code}/run/`,
        {
          method: "POST",
          body: args.payload != null
            ? JSON.stringify({ payload: args.payload })
            : undefined,
        },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fbr-scenarios"] });
      qc.invalidateQueries({ queryKey: ["fbr-status"] });
    },
  });
}

// ---------------------------------------------------------------------------
// Scenario payload templates — platform-level library for reusing
// working PRAL payloads when onboarding new tenants of similar types.
// ---------------------------------------------------------------------------

export interface FbrScenarioTemplate {
  id: string;
  name: string;
  scenario_code: string;
  notes: string;
  created_at: string;
  updated_at: string;
}

export function useFbrScenarioTemplates(scenarioCode?: string) {
  const qs = scenarioCode ? `?scenario_code=${scenarioCode}` : "";
  return useQuery({
    queryKey: ["fbr-scenario-templates", scenarioCode ?? "all"],
    queryFn: () =>
      api<{ results: FbrScenarioTemplate[] }>(
        `/fbr/scenarios/templates/${qs}`,
      ),
  });
}

// Save the current scenario payload as a reusable template. Super-
// admin only on the backend; the UI checks the same and hides the
// button for non-superusers.
export function useSaveScenarioTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      code: string;
      name: string;
      payload: unknown;
      notes?: string;
    }) =>
      api<{ id: string; name: string; scenario_code: string }>(
        `/fbr/scenarios/${args.code}/save-template/`,
        {
          method: "POST",
          body: JSON.stringify({
            name: args.name,
            payload: args.payload,
            notes: args.notes ?? "",
          }),
        },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fbr-scenario-templates"] });
    },
  });
}

// Apply a saved template to the current tenant + run against PRAL.
// The backend materialises the seller block from this tenant.
export function useApplyScenarioTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { code: string; templateId: string }) =>
      api<{ status: string; scenario: FbrScenarioRow | null }>(
        `/fbr/scenarios/${args.code}/apply-template/${args.templateId}/`,
        { method: "POST" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["fbr-scenarios"] });
      qc.invalidateQueries({ queryKey: ["fbr-status"] });
    },
  });
}


export interface FbrSubmissionRow {
  id: string;
  invoice: string | null;
  environment: "sandbox" | "production";
  endpoint: string;
  http_status: number | null;
  status_code: string | null;
  fbr_invoice_number: string | null;
  attempt_number: number;
  duration_ms: number | null;
  error_message: string | null;
  submitted_at: string;
  // request_payload + response_payload are the raw JSON dicts the
  // backend serializer returns — we treat them as `unknown` and only
  // JSON.stringify them for display in the FBR-log panel.
  request_payload: unknown;
  response_payload: unknown;
}

export function useFbrSubmissions(filters: { invoice?: string; status_code?: string } = {}) {
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) if (v) cleaned[k] = v;
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["fbr-submissions", filters],
    queryFn: () =>
      api<{ count: number; results: FbrSubmissionRow[] }>(
        `/fbr/submissions/${query ? `?${query}` : ""}`,
      ),
  });
}

export function useRetrySubmission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (invoiceId: string) =>
      api(`/fbr/submissions/retry/${invoiceId}/`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fbr-submissions"] }),
  });
}

export interface FbrCancelBudgetData {
  id: string;
  month_start: string;
  previous_month_sales: string;
  budget_amount: string;
  consumed_amount: string;
  remaining_amount: string;
  last_recalculated_at: string;
  consumptions: {
    id: string;
    invoice: string;
    consumption_type: "edit" | "cancel";
    amount: string;
    consumed_at: string;
  }[];
}

export function useFbrCancelBudget() {
  return useQuery({
    queryKey: ["fbr-cancel-budget"],
    queryFn: () => api<FbrCancelBudgetData>("/fbr/cancel-budget/"),
    refetchInterval: 30_000,
  });
}

export function useSubmitSandboxToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { token: string; api_endpoint?: string }) =>
      api("/fbr/tokens/sandbox/", {
        method: "POST", body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fbr-status"] }),
  });
}

export function useActivateProductionToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      token: string;
      api_endpoint?: string;
      // Platform-staff-only: activate a token FBR already issued (sandbox
      // cleared on the FBR portal) without our scenario runner being green.
      // The backend ignores this flag for non-platform users.
      scenarios_cleared_externally?: boolean;
    }) =>
      api("/fbr/tokens/production/", {
        method: "POST", body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fbr-status"] }),
  });
}

export interface TestTokenResult {
  ok: boolean;
  detail?: string;
  uom_count?: number;
  endpoint_base?: string;
}

/** Probe a candidate (token, endpoint) pair against PRAL without
 *  saving. Used by the FBR setup wizard's "Test connection" button. */
export function useTestFbrToken() {
  return useMutation({
    mutationFn: (body: { token: string; api_endpoint: string }) =>
      api<TestTokenResult>("/fbr/tokens/test/", {
        method: "POST", body: JSON.stringify(body),
      }),
  });
}

// ---------- Payments (Phase 5) ----------

export interface PaymentSettings {
  enabled_payment_methods: string[];
  easypaisa_merchant_id: string;
  easypaisa_qr_url: string;
  jazzcash_merchant_id: string;
  jazzcash_qr_url: string;
  raast_iban: string;
  raast_qr_url: string;
  bank_account_name: string;
  bank_account_iban: string;
  bank_account_bank: string;
  updated_at: string;
}

export function usePaymentSettings() {
  return useQuery({
    queryKey: ["payment-settings"],
    queryFn: () => api<PaymentSettings>("/payments/settings/"),
  });
}

export function useUpdatePaymentSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<PaymentSettings>) =>
      api<PaymentSettings>("/payments/settings/", {
        method: "PATCH", body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["payment-settings"] }),
  });
}

export interface ChequeRow {
  id: string;
  invoice: string | null;
  customer: string | null;
  amount: string;
  cheque_number: string | null;
  bank_name: string | null;
  cheque_date: string | null;
  cheque_status: "pending" | "cleared" | "bounced" | null;
  status: string;
  notes: string | null;
  created_at: string;
}

export function useCheques(statusFilter?: string) {
  const query = statusFilter ? `?status=${statusFilter}` : "";
  return useQuery({
    queryKey: ["cheques", statusFilter],
    queryFn: () =>
      api<{ count: number; results: ChequeRow[] }>(`/payments/cheques/${query}`),
  });
}

export function useClearCheque() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api(`/payments/cheques/${id}/clear/`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cheques"] }),
  });
}

export function useBounceCheque() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api(`/payments/cheques/${id}/bounce/`, {
        method: "POST", body: JSON.stringify({ reason }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cheques"] }),
  });
}

// ---------- Returns (Phase 6) ----------

export interface ReturnItemRow {
  id: string;
  original_sale_item: string;
  product: string;
  quantity: string;
  unit_price: string;
  tax_amount: string;
  line_total: string;
  restocked: boolean;
  movement_type: string;
}

export interface AdminReturn {
  id: string;
  branch: string;
  terminal: string;
  cashier: string;
  customer: string | null;
  original_invoice: string;
  return_number: string;
  fbr_credit_note_number: string | null;
  return_date: string;
  reason: string;
  reason_notes: string;
  refund_method: string;
  refund_amount: string;
  fbr_route: "amend" | "credit_note" | null;
  status: string;
  items: ReturnItemRow[];
  created_at: string;
  updated_at: string;
}

export function useReturns(filters: {
  branch?: string; refund_method?: string; from?: string; to?: string;
} = {}) {
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) if (v) cleaned[k] = v;
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["returns", filters],
    queryFn: () =>
      api<{ count: number; results: AdminReturn[] }>(
        `/returns/${query ? `?${query}` : ""}`,
      ),
  });
}

export function useReturn(id: string | undefined) {
  return useQuery({
    queryKey: ["return", id],
    queryFn: () => api<AdminReturn>(`/returns/${id}/`),
    enabled: !!id,
  });
}

// ----- Manual / Wholesaler invoice creation -----

export interface ManualInvoiceLine {
  product: string;
  quantity: string;
  unit_price: string;
  tax_rate: string;
  is_taxable: boolean;
  discount_amount?: string;
  hs_code?: string;
  uom_code?: string;
}

export interface ManualInvoicePayment {
  payment_method:
    | "cash" | "card_credit" | "card_debit"
    | "easypaisa" | "jazzcash" | "raast"
    | "cheque" | "bank_transfer" | "store_credit";
  amount: string;
  // Card (card_credit / card_debit) — last4 + auth_code required, rrn optional
  card_last4?: string;
  card_auth_code?: string;
  card_rrn?: string;
  card_terminal_id?: string;
  // Wallet (easypaisa / jazzcash)
  wallet_transaction_id?: string;
  // Raast
  raast_transaction_id?: string;
  // Cheque
  cheque_number?: string;
  bank_name?: string;
  cheque_date?: string;
  // Bank transfer (also uses bank_name)
  bank_reference?: string;
}

export interface ManualInvoiceInput {
  // Optional: when omitted, the server provisions an implicit default
  // branch + terminal (office-invoice tenants without those modules).
  branch?: string;
  terminal?: string;
  customer?: string | null;
  cart_lines: ManualInvoiceLine[];
  cart_discount_pct?: string;
  payments: ManualInvoicePayment[];
  client_uuid: string;
  notes?: string;
  /** Debit / credit note linkage. Defaults to "sale". Server requires
   *  `reference_invoice` when invoice_type is debit_note or credit_note. */
  invoice_type?: "sale" | "debit_note" | "credit_note";
  reference_invoice?: string | null;
}

export interface CreatedInvoice {
  id: string;
  local_invoice_number: string;
  fbr_invoice_number: string | null;
  status: string;
  grand_total: string;
  subtotal: string;
  tax_total: string;
  invoice_date: string;
}

export function useCreateManualInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ManualInvoiceInput) =>
      api<CreatedInvoice>("/sales/invoices/manual/", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sales"] });
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

// ----- Customers -----

export interface AdminCustomer {
  id: string;
  customer_code: string | null;
  name: string;
  phone: string | null;
  email: string | null;
  cnic: string | null;
  ntn: string | null;
  registration_type: "registered" | "unregistered";
  province: string | null;
  address: string;
  credit_limit: string;
  current_balance: string;
  store_credit: string;
  loyalty_points: number;
  is_active: boolean;
  notes: string;
  created_at: string;
}

export interface CustomerLedgerRow {
  id: string;
  customer: string;
  transaction_type: string;
  reference_type: string | null;
  reference_id: string | null;
  debit: string;
  credit: string;
  running_balance: string;
  notes: string | null;
  created_at: string;
}

export function useCustomers(filters: { search?: string; page?: number } = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.page) params.set("page", String(filters.page));
  const query = params.toString();
  const enabled = useModuleEnabled("customers");
  return useQuery({
    queryKey: ["customers", filters],
    queryFn: () =>
      api<{ count: number; results: AdminCustomer[] }>(
        `/customers/${query ? `?${query}` : ""}`,
      ),
    enabled,
    initialData: enabled
      ? undefined
      : ({ count: 0, results: [] } as { count: number; results: AdminCustomer[] }),
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useCustomer(id: string | undefined) {
  return useQuery({
    queryKey: ["customer", id],
    queryFn: () => api<AdminCustomer>(`/customers/${id}/`),
    enabled: !!id,
  });
}

export function useCustomerLedger(customerId: string | undefined) {
  return useQuery({
    queryKey: ["customer-ledger", customerId],
    queryFn: () =>
      api<{ count: number; results: CustomerLedgerRow[] }>(
        `/customers/ledger/?customer=${customerId}`,
      ),
    enabled: !!customerId,
  });
}

export function useUpsertCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<AdminCustomer> & { id?: string }) => {
      const { id, ...body } = input;
      return id
        ? api<AdminCustomer>(`/customers/${id}/`, {
            method: "PATCH",
            body: JSON.stringify(body),
          })
        : api<AdminCustomer>("/customers/", {
            method: "POST",
            body: JSON.stringify(body),
          });
    },
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ["customers"] });
      qc.invalidateQueries({ queryKey: ["customer", data.id] });
    },
  });
}

// ----- Reports (Phase 7) -----

export interface ReportColumn {
  key: string; label: string; kind: string; align?: string;
}

export interface ReportListEntry {
  name: string;
  columns: ReportColumn[];
  filter_fields: string[];
  chart: { type: string } | null;
}

export interface ReportPreview {
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, unknown>;
  chart: { type: string; x_key: string | null; y_keys: string[] } | null;
  row_count: number;
  truncated: boolean;
}

export interface DashboardData {
  kpis: {
    today_gross: string;
    today_count: number;
    today_refunds: number;
    avg_ticket: string;
  };
  sparkline: { date: string; gross: string }[];
  recent_invoices: Array<{
    id: string; local_invoice_number: string; branch: string;
    cashier: string; grand_total: string; status: string; created_at: string;
  }>;
  low_stock: Array<{
    sku: string; name: string; branch: string;
    quantity: string; reorder_level: string;
  }>;
  failed_fbr: Array<{
    id: string; invoice_number: string; status_code: string;
    error: string; submitted_at: string;
  }>;
  payment_breakdown: Array<{ method: string; total: string; count: number }>;
  freshness: { last_built_at: string | null };
}

export interface ReportFavorite {
  id: string;
  report_name: string;
  label: string;
  filters_json: Record<string, unknown>;
  created_at: string;
}

export function useReportRegistry() {
  return useQuery({
    queryKey: ["reports", "registry"],
    queryFn: () => api<{ results: ReportListEntry[] }>("/reports/"),
    staleTime: 1000 * 60 * 60,
  });
}

export function useDashboard() {
  return useQuery({
    queryKey: ["reports", "dashboard"],
    queryFn: () => api<DashboardData>("/reports/dashboard/"),
    refetchInterval: 1000 * 60 * 5, // 5 min
  });
}

export function useReportPreview() {
  return useMutation({
    mutationFn: ({ name, filters }: { name: string; filters: Record<string, unknown> }) =>
      api<ReportPreview>(`/reports/${name}/preview/`, {
        method: "POST",
        body: JSON.stringify(filters),
      }),
  });
}

export function useReportFavorites() {
  return useQuery({
    queryKey: ["reports", "favorites"],
    queryFn: () =>
      api<{ count: number; results: ReportFavorite[] }>("/reports/favorites/"),
  });
}

export function useSaveFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { report_name: string; label: string; filters_json: Record<string, unknown> }) =>
      api<ReportFavorite>("/reports/favorites/", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", "favorites"] }),
  });
}

export function useDeleteFavorite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api(`/reports/favorites/${id}/`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["reports", "favorites"] }),
  });
}


// ---------------------------------------------------------------------------
// Tenant self-serve setup (business mode + FBR nature + sector).
// Drives the onboarding wizard.
// ---------------------------------------------------------------------------

export type BusinessMode = "pos" | "digital_invoicing" | "both";

export interface TenantSetupChoices {
  business_modes: { value: BusinessMode; label: string }[];
  fbr_business_natures: string[];
  fbr_sectors: string[];
  likely_sector_for_nature: Record<string, string>;
}

export interface TenantSetup {
  business_mode: BusinessMode;
  fbr_business_natures: string[];
  fbr_sector: string | null;
  business_name: string;
  ntn: string;
  setup_complete: boolean;
  choices: TenantSetupChoices;
}

export function useTenantSetup() {
  return useQuery({
    queryKey: ["tenant-setup"],
    queryFn: () => api<TenantSetup>("/tenants/me/setup/"),
    // The wizard reads this on app boot; cache-friendly so it doesn't
    // refetch on every navigation. Will be re-fetched on save via
    // invalidate.
    staleTime: 5 * 60 * 1000,
  });
}

export interface SaveTenantSetupInput {
  business_mode?: BusinessMode;
  fbr_business_natures?: string[];
  fbr_sector?: string | null;
  /** First-time wizard sets this true to flip default modules. */
  apply_default_modules?: boolean;
}

export function useSaveTenantSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: SaveTenantSetupInput) =>
      api<TenantSetup>("/tenants/me/setup/", {
        method: "PATCH",
        body: JSON.stringify(input),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tenant-setup"] });
      // Modules may have flipped — refresh the catalog so the sidebar
      // updates without a full reload. NB: the actual query key in
      // features/modules/hooks.ts is "me-modules" (with the hyphen);
      // invalidating "modules" silently misses and the sidebar
      // stays on the previous list.
      qc.invalidateQueries({ queryKey: ["me-modules"] });
    },
  });
}
