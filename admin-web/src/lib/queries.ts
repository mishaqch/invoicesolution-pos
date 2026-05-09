import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  Branch, Category, HsCode, PosProduct, Product,
  StockAudit, StockLevel, StockMovement, StockTransfer,
  TaxRate, UnitOfMeasure,
} from "@pos/shared/types";

import { api } from "./api";

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
export function useBranches() {
  return useQuery({
    queryKey: ["branches"],
    queryFn: () => api<Page<Branch>>("/branches/"),
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
  terminal: string;
  cashier: string;
  customer: string | null;
  local_invoice_number: string;
  fbr_invoice_number: string | null;
  invoice_type: string;
  invoice_date: string;
  buyer_name: string | null;
  buyer_phone: string | null;
  subtotal: string;
  discount_total: string;
  tax_total: string;
  grand_total: string;
  paid_total: string;
  change_given: string;
  status: string;
  is_held: boolean;
  held_label: string | null;
  notes: string | null;
  items: InvoiceLine[];
  payments: InvoicePayment[];
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

export function useInvoice(id: string | undefined) {
  return useQuery({
    queryKey: ["invoice", id],
    queryFn: () => api<AdminInvoice>(`/sales/invoices/${id}/`),
    enabled: !!id,
  });
}

export function useCancelInvoice() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api<AdminInvoice>(`/sales/invoices/${id}/cancel/`, {
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
  return useQuery({
    queryKey: ["sync-status", terminalId],
    queryFn: () =>
      api<{ results: TerminalSyncStatus[] }>(
        `/sync/status/${terminalId ? `?terminal_id=${terminalId}` : ""}`,
      ),
    refetchInterval: 5000,
  });
}

export function useSyncLog(filters: { terminal_id?: string; status?: string } = {}) {
  const cleaned: Record<string, string> = {};
  for (const [k, v] of Object.entries(filters)) if (v) cleaned[k] = v;
  const query = new URLSearchParams(cleaned).toString();
  return useQuery({
    queryKey: ["sync-log", filters],
    queryFn: () =>
      api<{ count: number; results: SyncLogEntry[] }>(
        `/sync/log/${query ? `?${query}` : ""}`,
      ),
    refetchInterval: 5000,
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
  device_fingerprint: string;
  os_version: string | null;
  app_version: string | null;
  is_active: boolean;
  last_seen_at: string | null;
  last_synced_at: string | null;
  customer_display_enabled: boolean;
}

export function useTerminals() {
  return useQuery({
    queryKey: ["terminals"],
    queryFn: () => api<{ count: number; results: AdminTerminal[] }>("/terminals/"),
  });
}

// ---------- FBR (Phase 4) ----------

export interface FbrTokenInfo {
  id: string;
  environment: "sandbox" | "production";
  api_endpoint: string;
  is_active: boolean;
  has_token: boolean;
  activated_at: string | null;
  expires_at: string | null;
}

export interface FbrStatus {
  tenant_id: string;
  environment: "sandbox" | "production" | "none";
  sandbox: FbrTokenInfo | null;
  production: FbrTokenInfo | null;
  last_successful_submission_at: string | null;
  eligible_scenarios: { code: string; description: string }[];
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

export interface FbrScenarioRow {
  id: string;
  scenario_code: string;
  scenario_description: string;
  status: "pending" | "submitting" | "success" | "failed";
  fbr_invoice_number: string | null;
  last_attempt_at: string | null;
  error_message: string | null;
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
    mutationFn: (body: { token: string; api_endpoint?: string }) =>
      api("/fbr/tokens/production/", {
        method: "POST", body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["fbr-status"] }),
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
    | "cash" | "card" | "easypaisa" | "jazzcash" | "raast"
    | "cheque" | "bank_transfer" | "store_credit" | "credit";
  amount: string;
  reference?: string;
  cheque_number?: string | null;
  cheque_bank?: string | null;
  cheque_due_date?: string | null;
  cheque_status?: string | null;
}

export interface ManualInvoiceInput {
  branch: string;
  terminal: string;
  customer?: string | null;
  cart_lines: ManualInvoiceLine[];
  cart_discount_pct?: string;
  payments: ManualInvoicePayment[];
  client_uuid: string;
  notes?: string;
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
  return useQuery({
    queryKey: ["customers", filters],
    queryFn: () =>
      api<{ count: number; results: AdminCustomer[] }>(
        `/customers/${query ? `?${query}` : ""}`,
      ),
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
