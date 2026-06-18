import { QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { queryClient } from "@/lib/queryClient";

import { AdminShell } from "@/components/layout/AdminShell";
import { ToastProvider } from "@/components/feedback/Toast";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import { RequireModule } from "@/features/modules/RequireModule";
import { RequireDiApi } from "@/features/modules/RequireDiApi";
import { RequireVertical } from "@/features/modules/RequireVertical";
import BranchesList from "@/routes/branches/branches";
import TerminalsList from "@/routes/terminals/terminals";
import CategoriesList from "@/routes/catalog/categories";
import CsvImport from "@/routes/catalog/csv-import";
import HsCodesBrowser from "@/routes/catalog/hs-codes";
import ProductEdit from "@/routes/catalog/product-edit";
import ProductsList from "@/routes/catalog/products";
import TaxRatesList from "@/routes/catalog/tax-rates";
import DashboardRoute from "@/routes/dashboard";
import Adjustments from "@/routes/inventory/adjustments";
import StockAuditsList from "@/routes/inventory/audits";
import ExpiryList from "@/routes/inventory/expiry";
import FbrReadinessList from "@/routes/inventory/fbr-readiness";
import Movements from "@/routes/inventory/movements";
import RestockList from "@/routes/inventory/restock";
import SuppliersList from "@/routes/suppliers/list";
import ReceiveStock from "@/routes/purchases/receive";
import TablesAdmin from "@/routes/restaurant/tables";
import ModifiersAdmin from "@/routes/restaurant/modifiers";
import FloorView from "@/routes/restaurant/floor";
import KitchenDisplay from "@/routes/restaurant/kitchen";
import StockByBranch from "@/routes/inventory/stock-by-branch";
import StockByWarehouse from "@/routes/inventory/stock-by-warehouse";
import Warehouses from "@/routes/inventory/warehouses";
import StockTransfersList from "@/routes/inventory/transfers";
import LoginRoute from "@/routes/login";
import HeldSalesAdminList from "@/routes/sales/held-sales";
import NewInvoiceRoute from "@/routes/sales/new";
import InvoiceDetail from "@/routes/sales/invoice-detail";
import InvoicesList from "@/routes/sales/invoices";
import SyncHealth from "@/routes/sync/sync-health";
import TerminalSyncDetail from "@/routes/sync/terminal-detail";
import CancelBudgetPage from "@/routes/fbr/cancel-budget";
import FbrDashboard from "@/routes/fbr/dashboard";
import ManualAmendmentPage from "@/routes/fbr/manual-amendment";
import ScenariosPage from "@/routes/fbr/scenarios";
import FbrSetupWizard from "@/routes/fbr/setup";
import SubmissionsPage from "@/routes/fbr/submissions";
import ChequesPage from "@/routes/payments/cheques";
import PaymentSettingsPage from "@/routes/payments/settings";
import CustomerDetail from "@/routes/customers/detail";
import CustomerImportRoute from "@/routes/customers/import";
import CustomersList from "@/routes/customers/list";
import HelpCenter from "@/routes/help";
import BusinessProfileRoute from "@/routes/settings/business-profile";
import HardwareChecklist from "@/routes/settings/hardware";
import SettingsIndex from "@/routes/settings";
import ReportDetail from "@/routes/reports/detail";
import ReportsIndex from "@/routes/reports";
import ReturnDetail from "@/routes/returns/detail";
import ReturnsList from "@/routes/returns/list";

// The QueryClient now lives in @/lib/queryClient so the auth store can clear
// its cache on login/logout (see queryClient.ts).

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
      <BrowserRouter>
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
      </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

