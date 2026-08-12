import { useEffect } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import { ToastProvider } from "@/components/feedback/Toast";
import { TextPromptHost } from "@/components/ui/TextPromptModal";
import { UpdateBanner } from "@/features/updates/UpdateBanner";
import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import DayCloseRoute from "@/routes/day-close";
import DayOpenRoute from "@/routes/day-open";
import HardwareRoute from "@/routes/hardware";
import HeldSalesRoute from "@/routes/held-sales";
import TodayInvoicesRoute from "@/routes/today-invoices";
import LoginRoute from "@/routes/login";
import PairingRoute from "@/routes/pairing";
import PaymentRoute from "@/routes/payment";
import ReturnRoute from "@/routes/return";
import SaleRoute from "@/routes/sale";
import SplashRoute from "@/routes/splash";
import StaysRoute from "@/routes/stays";
import SuccessRoute from "@/routes/success";
import SyncPendingRoute from "@/routes/sync-pending";

const protectedRoute = (el: React.ReactNode) => (
  <ProtectedRoute>{el}</ProtectedRoute>
);

export default function App() {
  // Cheap renderer-side reconnect trigger: when the OS reports the network is
  // back, tell the sync worker to expedite (drain the queue immediately rather
  // than waiting out its backoff). The main-process reachability poll +
  // powerMonitor are the authoritative triggers; this is a free third one.
  useEffect(() => {
    const onOnline = () => void window.api?.sync?.expedite?.();
    window.addEventListener("online", onOnline);
    return () => window.removeEventListener("online", onOnline);
  }, []);

  return (
    <HashRouter>
      <ToastProvider>
      <Routes>
        <Route path="/" element={<SplashRoute />} />
        <Route path="/pairing" element={<PairingRoute />} />
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/day-open" element={protectedRoute(<DayOpenRoute />)} />
        <Route path="/sale" element={protectedRoute(<SaleRoute />)} />
        <Route path="/payment" element={protectedRoute(<PaymentRoute />)} />
        <Route path="/success" element={protectedRoute(<SuccessRoute />)} />
        <Route path="/held-sales" element={protectedRoute(<HeldSalesRoute />)} />
        <Route path="/stays" element={protectedRoute(<StaysRoute />)} />
        <Route path="/today-invoices" element={protectedRoute(<TodayInvoicesRoute />)} />
        <Route path="/sync" element={protectedRoute(<SyncPendingRoute />)} />
        <Route path="/return" element={protectedRoute(<ReturnRoute />)} />
        <Route path="/day-close" element={protectedRoute(<DayCloseRoute />)} />
        <Route path="/hardware" element={protectedRoute(<HardwareRoute />)} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {/* App-wide in-app text prompt (replaces Electron's missing window.prompt). */}
      <TextPromptHost />
      {/* App-wide banner: tells the cashier when a new version is ready. */}
      <UpdateBanner />
      </ToastProvider>
    </HashRouter>
  );
}
