import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AdminShell } from "@/components/layout/AdminShell";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import BranchesList from "@/routes/branches/branches";
import CategoriesList from "@/routes/catalog/categories";
import CsvImport from "@/routes/catalog/csv-import";
import HsCodesBrowser from "@/routes/catalog/hs-codes";
import ProductEdit from "@/routes/catalog/product-edit";
import ProductsList from "@/routes/catalog/products";
import TaxRatesList from "@/routes/catalog/tax-rates";
import DashboardRoute from "@/routes/dashboard";
import Adjustments from "@/routes/inventory/adjustments";
import Movements from "@/routes/inventory/movements";
import StockByBranch from "@/routes/inventory/stock-by-branch";
import LoginRoute from "@/routes/login";
import HeldSalesAdminList from "@/routes/sales/held-sales";
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
import ReturnDetail from "@/routes/returns/detail";
import ReturnsList from "@/routes/returns/list";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
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

            <Route path="branches" element={<BranchesList />} />

            <Route path="catalog">
              <Route path="products" element={<ProductsList />} />
              <Route path="products/import" element={<CsvImport />} />
              <Route path="products/new" element={<ProductEdit />} />
              <Route path="products/:id" element={<ProductEdit />} />
              <Route path="categories" element={<CategoriesList />} />
              <Route path="tax-rates" element={<TaxRatesList />} />
              <Route path="hs-codes" element={<HsCodesBrowser />} />
            </Route>

            <Route path="inventory">
              <Route path="stock" element={<StockByBranch />} />
              <Route path="movements" element={<Movements />} />
              <Route path="adjustments" element={<Adjustments />} />
            </Route>

            <Route path="sales">
              <Route index element={<InvoicesList />} />
              <Route path="held" element={<HeldSalesAdminList />} />
              <Route path=":id" element={<InvoiceDetail />} />
            </Route>

            <Route path="sync">
              <Route index element={<SyncHealth />} />
              <Route path="terminals/:id" element={<TerminalSyncDetail />} />
            </Route>

            <Route path="fbr">
              <Route index element={<FbrDashboard />} />
              <Route path="setup" element={<FbrSetupWizard />} />
              <Route path="scenarios" element={<ScenariosPage />} />
              <Route path="submissions" element={<SubmissionsPage />} />
              <Route path="cancel-budget" element={<CancelBudgetPage />} />
              <Route path="manual-amendment" element={<ManualAmendmentPage />} />
            </Route>

            <Route path="payments">
              <Route path="settings" element={<PaymentSettingsPage />} />
              <Route path="cheques" element={<ChequesPage />} />
            </Route>

            <Route path="returns">
              <Route index element={<ReturnsList />} />
              <Route path=":id" element={<ReturnDetail />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

