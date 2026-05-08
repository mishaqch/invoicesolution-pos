import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

export default function SplashRoute() {
  const navigate = useNavigate();
  useEffect(() => {
    const t = window.setTimeout(() => navigate("/login", { replace: true }), 600);
    return () => window.clearTimeout(t);
  }, [navigate]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="text-3xl font-semibold tracking-tight">Pakistan POS</div>
        <div className="mt-2 text-sm text-muted-foreground">Loading…</div>
      </div>
    </div>
  );
}
