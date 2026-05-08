import { HashRouter, Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "@/features/auth/ProtectedRoute";
import LoginRoute from "@/routes/login";
import SaleRoute from "@/routes/sale";
import SplashRoute from "@/routes/splash";

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<SplashRoute />} />
        <Route path="/login" element={<LoginRoute />} />
        <Route
          path="/sale"
          element={
            <ProtectedRoute>
              <SaleRoute />
            </ProtectedRoute>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  );
}
