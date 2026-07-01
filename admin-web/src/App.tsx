import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { queryClient } from "@/lib/queryClient";

import { AdminShell } from "@/components/layout/AdminShell";
import { ToastProvider } from "@/components/feedback/Toast";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RequireModule } from "@/features/modules/RequireModule";
import { RequireDiApi } from "@/features/modules/RequireDiApi";
import { RequireVertical } from "@/features/modules/RequireVertical";

// Every page is lazily imported so the first load only downloads the shell +
// the page actually being viewed — not all 50+ screens at once. This is the
// biggest single win for slow links (e.g. Pakistan): the login/dashboard chunk
// is a fraction of the old single 468 KB bundle. Each route is its own
// content-hashed chunk, cached immutably + brotli-compressed by nginx.
const LoginRoute = lazy(() => import("@/routes/login"));
const BranchesList = lazy(() => import("@/routes/branches/branches"));
const TerminalsList = lazy(() => import("@/routes/terminals/terminals"));
const CategoriesList = lazy(() => import("@/routes/catalog/categories"));
const CsvImport = lazy(() => import("@/routes/catalog/csv-import"));
const HsCodesBrowser = lazy(() => import("@/routes/catalog/hs-codes"));
const ProductEdit = lazy(() => import("@/routes/catalog/product-edit"));
const ProductsList = lazy(() => import("@/routes/catalog/products"));
const TaxRatesList = lazy(() => import("@/routes/catalog/tax-rates"));
const DashboardRoute = lazy(() => import("@/routes/dashboard"));
const Adjustments = lazy(() => import("@/routes/inventory/adjustments"));
const StockAuditsList = lazy(() => import("@/routes/inventory/audits"));
const ExpiryList = lazy(() => import("@/routes/inventory/expiry"));
const FbrReadinessList = lazy(() => import("@/routes/inventory/fbr-readiness"));
const Movements = lazy(() => import("@/routes/inventory/movements"));
const RestockList = lazy(() => import("@/routes/inventory/restock"));
const SuppliersList = lazy(() => import("@/routes/suppliers/list"));
const ReceiveStock = lazy(() => import("@/routes/purchases/receive"));
const TablesAdmin = lazy(() => import("@/routes/restaurant/tables"));
const RoomsAdmin = lazy(() => import("@/routes/hotel/rooms"));
const StaysAdmin = lazy(() => import("@/routes/hotel/stays"));
const ModifiersAdmin = lazy(() => import("@/routes/restaurant/modifiers"));
const FloorView = lazy(() => import("@/routes/restaurant/floor"));
const KitchenDisplay = lazy(() => import("@/routes/restaurant/kitchen"));
const StockByBranch = lazy(() => import("@/routes/inventory/stock-by-branch"));
const StockByWarehouse = lazy(() => import("@/routes/inventory/stock-by-warehouse"));
const Warehouses = lazy(() => import("@/routes/inventory/warehouses"));
const StockTransfersList = lazy(() => import("@/routes/inventory/transfers"));
const HeldSalesAdminList = lazy(() => import("@/routes/sales/held-sales"));
const NewInvoiceRoute = lazy(() => import("@/routes/sales/new"));
const InvoiceDetail = lazy(() => import("@/routes/sales/invoice-detail"));
const InvoicesList = lazy(() => import("@/routes/sales/invoices"));
const SyncHealth = lazy(() => import("@/routes/sync/sync-health"));
const TerminalSyncDetail = lazy(() => import("@/routes/sync/terminal-detail"));
const CancelBudgetPage = lazy(() => import("@/routes/fbr/cancel-budget"));
const FbrDashboard = lazy(() => import("@/routes/fbr/dashboard"));
const ManualAmendmentPage = lazy(() => import("@/routes/fbr/manual-amendment"));
const ScenariosPage = lazy(() => import("@/routes/fbr/scenarios"));
const FbrSetupWizard = lazy(() => import("@/routes/fbr/setup"));
const SubmissionsPage = lazy(() => import("@/routes/fbr/submissions"));
const ChequesPage = lazy(() => import("@/routes/payments/cheques"));
const PaymentSettingsPage = lazy(() => import("@/routes/payments/settings"));
const CustomerDetail = lazy(() => import("@/routes/customers/detail"));
const CustomerImportRoute = lazy(() => import("@/routes/customers/import"));
const CustomersList = lazy(() => import("@/routes/customers/list"));
const HelpCenter = lazy(() => import("@/routes/help"));
const BusinessProfileRoute = lazy(() => import("@/routes/settings/business-profile"));
const HardwareChecklist = lazy(() => import("@/routes/settings/hardware"));
const SettingsIndex = lazy(() => import("@/routes/settings"));
const ReportDetail = lazy(() => import("@/routes/reports/detail"));
const ReportsIndex = lazy(() => import("@/routes/reports"));
const ReturnDetail = lazy(() => import("@/routes/returns/detail"));
const ReturnsList = lazy(() => import("@/routes/returns/list"));

// The QueryClient now lives in @/lib/queryClient so the auth store can clear
// its cache on login/logout (see queryClient.ts).

/** Shown briefly while a lazily-loaded page chunk downloads. */
function RouteFallback() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary" />
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
      <BrowserRouter>
        <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />

          <Route
            path="/"
            element={
              <ProtectedRoute>
                <AdminShell>
                  <Outlet />
                </AdminShell>
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardRoute />} />

            <Route
              path="branches"
              element={<RequireModule module="branches"><BranchesList /></RequireModule>}
            />
            <Route
              path="terminals"
              element={<RequireModule module="terminals"><TerminalsList /></RequireModule>}
            />

            <Route path="catalog">
              <Route path="products" element={<ProductsList />} />
              <Route path="products/import" element={<CsvImport />} />
              <Route path="products/new" element={<ProductEdit />} />
              <Route path="products/:id" element={<ProductEdit />} />
              <Route path="categories" element={<CategoriesList />} />
              <Route path="tax-rates" element={<TaxRatesList />} />
              <Route path="hs-codes" element={<HsCodesBrowser />} />
            </Route>

            <Route
              path="inventory"
              element={<RequireModule module="inventory"><Outlet /></RequireModule>}
            >
              <Route path="stock" element={<StockByBranch />} />
              <Route path="restock" element={<RestockList />} />
              <Route
                path="expiry"
                element={<RequireVertical vertical="pharmacy"><ExpiryList /></RequireVertical>}
              />
              <Route path="movements" element={<Movements />} />
              <Route path="adjustments" element={<Adjustments />} />
              <Route path="transfers" element={<StockTransfersList />} />
              <Route path="audits" element={<StockAuditsList />} />
            </Route>

            {/* Warehouses — Digital-Invoicing multi-godown stock. Gated by the
                `warehouses` module (off for POS), separate from the `inventory`
                group above so DI tenants (who lack `inventory`) can reach it. */}
            <Route
              path="inventory"
              element={<RequireModule module="warehouses"><Outlet /></RequireModule>}
            >
              <Route path="warehouses" element={<Warehouses />} />
              <Route path="warehouse-stock" element={<StockByWarehouse />} />
            </Route>

            {/* FBR readiness — products with an incomplete fiscal identity.
                Shared by POS (`inventory`) and Digital-Invoicing (`warehouses`)
                tenants, so it's gated any-of rather than living in either group. */}
            <Route
              path="inventory/fbr-readiness"
              element={
                <RequireModule anyOf={["inventory", "warehouses"]}>
                  <FbrReadinessList />
                </RequireModule>
              }
            />

            {/* Procurement — pharmacy/wholesale. Gated by inventory module +
                pharmacy vertical (the only vertical that surfaces it for now). */}
            <Route
              path="suppliers"
              element={
                <RequireModule module="inventory">
                  <RequireVertical vertical="pharmacy"><SuppliersList /></RequireVertical>
                </RequireModule>
              }
            />
            <Route
              path="purchases/receive"
              element={
                <RequireModule module="inventory">
                  <RequireVertical vertical="pharmacy"><ReceiveStock /></RequireVertical>
                </RequireModule>
              }
            />

            {/* Restaurant — F&B vertical. Gated by restaurant module + vertical. */}
            <Route
              path="restaurant"
              element={
                <RequireModule module="restaurant">
                  <RequireVertical vertical="restaurant"><Outlet /></RequireVertical>
                </RequireModule>
              }
            >
              <Route path="tables" element={<TablesAdmin />} />
              <Route path="modifiers" element={<ModifiersAdmin />} />
              <Route path="floor" element={<FloorView />} />
              <Route path="kitchen" element={<KitchenDisplay />} />
            </Route>

            {/* Hotel — rooms + guest folios. Gated by the opt-in `hotel` module
                (rooms+restaurant clients only). */}
            <Route path="hotel" element={<RequireModule module="hotel"><Outlet /></RequireModule>}>
              <Route path="rooms" element={<RoomsAdmin />} />
              <Route path="stays" element={<StaysAdmin />} />
            </Route>

            <Route path="sales">
              <Route index element={<InvoicesList />} />
              <Route path="new" element={<NewInvoiceRoute />} />
              <Route path="held" element={<HeldSalesAdminList />} />
              <Route path=":id" element={<InvoiceDetail />} />
            </Route>

            <Route path="sync">
              <Route index element={<SyncHealth />} />
              <Route path="terminals/:id" element={<TerminalSyncDetail />} />
            </Route>

            <Route path="fbr">
              <Route index element={<FbrDashboard />} />
              {/* Setup + Scenarios are DI-API only — IMS/SDC tenants are
                  redirected to the FBR dashboard. */}
              <Route path="setup" element={<RequireDiApi><FbrSetupWizard /></RequireDiApi>} />
              <Route path="scenarios" element={<RequireDiApi><ScenariosPage /></RequireDiApi>} />
              <Route path="submissions" element={<SubmissionsPage />} />
              <Route path="cancel-budget" element={<CancelBudgetPage />} />
              <Route path="manual-amendment" element={<ManualAmendmentPage />} />
            </Route>

            <Route path="payments">
              <Route path="settings" element={<PaymentSettingsPage />} />
              <Route
                path="cheques"
                element={<RequireModule module="payments_advanced"><ChequesPage /></RequireModule>}
              />
            </Route>

            <Route
              path="returns"
              element={<RequireModule module="returns"><Outlet /></RequireModule>}
            >
              <Route index element={<ReturnsList />} />
              <Route path=":id" element={<ReturnDetail />} />
            </Route>

            <Route
              path="customers"
              element={<RequireModule module="customers"><Outlet /></RequireModule>}
            >
              <Route index element={<CustomersList />} />
              <Route path="new" element={<CustomerDetail />} />
              <Route path="import" element={<CustomerImportRoute />} />
              <Route path=":id" element={<CustomerDetail />} />
            </Route>

            <Route
              path="reports"
              element={<RequireModule module="reports_basic"><Outlet /></RequireModule>}
            >
              <Route index element={<ReportsIndex />} />
              <Route path=":name" element={<ReportDetail />} />
            </Route>

            <Route path="help">
              <Route index element={<HelpCenter />} />
              <Route path=":slug" element={<HelpCenter />} />
            </Route>

            <Route path="settings">
              <Route index element={<SettingsIndex />} />
              <Route path="business-profile" element={<BusinessProfileRoute />} />
              <Route
                path="hardware"
                element={<RequireModule module="hardware"><HardwareChecklist /></RequireModule>}
              />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

