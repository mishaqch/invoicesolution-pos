import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import DayCloseRoute from "@/routes/day-close";
import DayOpenRoute from "@/routes/day-open";
import HeldSalesRoute from "@/routes/held-sales";
import TodayInvoicesRoute from "@/routes/today-invoices";
import LoginRoute from "@/routes/login";
import PaymentRoute from "@/routes/payment";
import ReturnRoute from "@/routes/return";
import SaleRoute from "@/routes/sale";
import SplashRoute from "@/routes/splash";
import SuccessRoute from "@/routes/success";

const protectedRoute = (el: React.ReactNode) => (
  <ProtectedRoute>{el}</ProtectedRoute>
);

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<SplashRoute />} />
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/day-open" element={protectedRoute(<DayOpenRoute />)} />
        <Route path="/sale" element={protectedRoute(<SaleRoute />)} />
        <Route path="/payment" element={protectedRoute(<PaymentRoute />)} />
        <Route path="/success" element={protectedRoute(<SuccessRoute />)} />
        <Route path="/held-sales" element={protectedRoute(<HeldSalesRoute />)} />
        <Route path="/today-invoices" element={protectedRoute(<TodayInvoicesRoute />)} />
        <Route path="/return" element={protectedRoute(<ReturnRoute />)} />
        <Route path="/day-close" element={protectedRoute(<DayCloseRoute />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
