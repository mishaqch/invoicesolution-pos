import { QueryClientProvider } from "@tanstack/react-query";
import { Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { queryClient } from "@/lib/queryClient";
import { lazyWithReload } from "@/lib/lazyWithReload";

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
const LoginRoute = lazyWithReload(() => import("@/routes/login"), "@/routes/login");
const BranchesList = lazyWithReload(() => import("@/routes/branches/branches"), "@/routes/branches/branches");
const TerminalsList = lazyWithReload(() => import("@/routes/terminals/terminals"), "@/routes/terminals/terminals");
const CategoriesList = lazyWithReload(() => import("@/routes/catalog/categories"), "@/routes/catalog/categories");
const CsvImport = lazyWithReload(() => import("@/routes/catalog/csv-import"), "@/routes/catalog/csv-import");
const HsCodesBrowser = lazyWithReload(() => import("@/routes/catalog/hs-codes"), "@/routes/catalog/hs-codes");
const ProductEdit = lazyWithReload(() => import("@/routes/catalog/product-edit"), "@/routes/catalog/product-edit");
const ProductsList = lazyWithReload(() => import("@/routes/catalog/products"), "@/routes/catalog/products");
const TaxRatesList = lazyWithReload(() => import("@/routes/catalog/tax-rates"), "@/routes/catalog/tax-rates");
const DashboardRoute = lazyWithReload(() => import("@/routes/dashboard"), "@/routes/dashboard");
const Adjustments = lazyWithReload(() => import("@/routes/inventory/adjustments"), "@/routes/inventory/adjustments");
const StockAuditsList = lazyWithReload(() => import("@/routes/inventory/audits"), "@/routes/inventory/audits");
const ExpiryList = lazyWithReload(() => import("@/routes/inventory/expiry"), "@/routes/inventory/expiry");
const FbrReadinessList = lazyWithReload(() => import("@/routes/inventory/fbr-readiness"), "@/routes/inventory/fbr-readiness");
const Movements = lazyWithReload(() => import("@/routes/inventory/movements"), "@/routes/inventory/movements");
const RestockList = lazyWithReload(() => import("@/routes/inventory/restock"), "@/routes/inventory/restock");
const SuppliersList = lazyWithReload(() => import("@/routes/suppliers/list"), "@/routes/suppliers/list");
const ReceiveStock = lazyWithReload(() => import("@/routes/purchases/receive"), "@/routes/purchases/receive");
const TablesAdmin = lazyWithReload(() => import("@/routes/restaurant/tables"), "@/routes/restaurant/tables");
const RoomsAdmin = lazyWithReload(() => import("@/routes/hotel/rooms"), "@/routes/hotel/rooms");
const StaysAdmin = lazyWithReload(() => import("@/routes/hotel/stays"), "@/routes/hotel/stays");
const ModifiersAdmin = lazyWithReload(() => import("@/routes/restaurant/modifiers"), "@/routes/restaurant/modifiers");
const FloorView = lazyWithReload(() => import("@/routes/restaurant/floor"), "@/routes/restaurant/floor");
const KitchenDisplay = lazyWithReload(() => import("@/routes/restaurant/kitchen"), "@/routes/restaurant/kitchen");
const StockByBranch = lazyWithReload(() => import("@/routes/inventory/stock-by-branch"), "@/routes/inventory/stock-by-branch");
const StockByWarehouse = lazyWithReload(() => import("@/routes/inventory/stock-by-warehouse"), "@/routes/inventory/stock-by-warehouse");
const Warehouses = lazyWithReload(() => import("@/routes/inventory/warehouses"), "@/routes/inventory/warehouses");
const StockTransfersList = lazyWithReload(() => import("@/routes/inventory/transfers"), "@/routes/inventory/transfers");
const HeldSalesAdminList = lazyWithReload(() => import("@/routes/sales/held-sales"), "@/routes/sales/held-sales");
const NewInvoiceRoute = lazyWithReload(() => import("@/routes/sales/new"), "@/routes/sales/new");
const InvoiceDetail = lazyWithReload(() => import("@/routes/sales/invoice-detail"), "@/routes/sales/invoice-detail");
const InvoicesList = lazyWithReload(() => import("@/routes/sales/invoices"), "@/routes/sales/invoices");
const SyncHealth = lazyWithReload(() => import("@/routes/sync/sync-health"), "@/routes/sync/sync-health");
const TerminalSyncDetail = lazyWithReload(() => import("@/routes/sync/terminal-detail"), "@/routes/sync/terminal-detail");
const CancelBudgetPage = lazyWithReload(() => import("@/routes/fbr/cancel-budget"), "@/routes/fbr/cancel-budget");
const FbrDashboard = lazyWithReload(() => import("@/routes/fbr/dashboard"), "@/routes/fbr/dashboard");
const ManualAmendmentPage = lazyWithReload(() => import("@/routes/fbr/manual-amendment"), "@/routes/fbr/manual-amendment");
const ScenariosPage = lazyWithReload(() => import("@/routes/fbr/scenarios"), "@/routes/fbr/scenarios");
const FbrSetupWizard = lazyWithReload(() => import("@/routes/fbr/setup"), "@/routes/fbr/setup");
const SubmissionsPage = lazyWithReload(() => import("@/routes/fbr/submissions"), "@/routes/fbr/submissions");
const ChequesPage = lazyWithReload(() => import("@/routes/payments/cheques"), "@/routes/payments/cheques");
const PaymentSettingsPage = lazyWithReload(() => import("@/routes/payments/settings"), "@/routes/payments/settings");
const CustomerDetail = lazyWithReload(() => import("@/routes/customers/detail"), "@/routes/customers/detail");
const CustomerImportRoute = lazyWithReload(() => import("@/routes/customers/import"), "@/routes/customers/import");
const CustomersList = lazyWithReload(() => import("@/routes/customers/list"), "@/routes/customers/list");
const HelpCenter = lazyWithReload(() => import("@/routes/help"), "@/routes/help");
const BusinessProfileRoute = lazyWithReload(() => import("@/routes/settings/business-profile"), "@/routes/settings/business-profile");
const HardwareChecklist = lazyWithReload(() => import("@/routes/settings/hardware"), "@/routes/settings/hardware");
const SettingsIndex = lazyWithReload(() => import("@/routes/settings"), "@/routes/settings");
const ReportDetail = lazyWithReload(() => import("@/routes/reports/detail"), "@/routes/reports/detail");
const ReportsIndex = lazyWithReload(() => import("@/routes/reports"), "@/routes/reports");
const ReturnDetail = lazyWithReload(() => import("@/routes/returns/detail"), "@/routes/returns/detail");
const ReturnsList = lazyWithReload(() => import("@/routes/returns/list"), "@/routes/returns/list");

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

