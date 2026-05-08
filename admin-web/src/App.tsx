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
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

