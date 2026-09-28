import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { queryClient } from "@/lib/queryClient";
import { ToastProvider } from "@/components/feedback/Toast";
import { useAuthStore } from "@/stores/auth";
import { useDeviceStore } from "@/stores/device";

// Lazy-load each route so the first paint only ships the shell + the current
// screen (mirrors admin-web's code-splitting).
const PairingRoute = lazy(() => import("@/routes/pairing"));
const StaffSelectRoute = lazy(() => import("@/routes/staff-select"));
const PinRoute = lazy(() => import("@/routes/pin"));
const OrderTakingRoute = lazy(() => import("@/routes/order-taking"));
const OrdersRoute = lazy(() => import("@/routes/orders"));

function RouteFallback() {
  return (
    <div className="center-fill">
      <div className="page-spin" aria-label="Loading" role="status" />
    </div>
  );
}

/** Blocks everything until the device is paired. */
function RequirePairing({ children }: { children: ReactNode }) {
  const terminalId = useDeviceStore((s) => s.terminalId);
  if (!terminalId) return <Navigate to="/pairing" replace />;
  return <>{children}</>;
}

/** Requires a signed-in waiter (device already paired). */
function RequireWaiterAuth({ children }: { children: ReactNode }) {
  const terminalId = useDeviceStore((s) => s.terminalId);
  const access = useAuthStore((s) => s.access);
  if (!terminalId) return <Navigate to="/pairing" replace />;
  if (!access) return <Navigate to="/staff" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/pairing" element={<PairingRoute />} />
            <Route
              path="/staff"
              element={
                <RequirePairing>
                  <StaffSelectRoute />
                </RequirePairing>
              }
            />
            <Route
              path="/pin"
              element={
                <RequirePairing>
                  <PinRoute />
                </RequirePairing>
              }
            />
            <Route
              path="/"
              element={
                <RequireWaiterAuth>
                  <OrderTakingRoute />
                </RequireWaiterAuth>
              }
            />
            <Route
              path="/orders"
              element={
                <RequireWaiterAuth>
                  <OrdersRoute />
                </RequireWaiterAuth>
              }
            />
            {/* Catch-all -> order-taking (guards bounce onward as needed). */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
      <ToastProvider />
    </QueryClientProvider>
  );
}
