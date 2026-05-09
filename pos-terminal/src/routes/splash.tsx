import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { LanguageToggle } from "@/components/LanguageToggle";

export default function SplashRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  useEffect(() => {
    const timeout = window.setTimeout(() => navigate("/login", { replace: true }), 600);
    return () => window.clearTimeout(timeout);
  }, [navigate]);

  return (
    <div className="relative flex min-h-screen items-center justify-center">
      <div className="absolute right-4 top-4">
        <LanguageToggle />
      </div>
      <div className="text-center">
        <div className="text-3xl font-semibold tracking-tight">Pakistan POS</div>
        <div className="mt-2 text-sm text-muted-foreground">{t("common.loading")}</div>
      </div>
    </div>
  );
}
