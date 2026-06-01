import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { LanguageToggle } from "@/components/LanguageToggle";

export default function SplashRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  useEffect(() => {
    let cancelled = false;
    const timeout = window.setTimeout(async () => {
      // Route to pairing on first launch (no branch/terminal bound yet),
      // otherwise straight to cashier login.
      let dest = "/pairing";
      try {
        const status = await window.api.pairing.status();
        if (status.paired) dest = "/login";
      } catch {
        // If the bridge isn't ready, fall through to pairing — it's the safe
        // default for an unconfigured terminal.
      }
      if (!cancelled) navigate(dest, { replace: true });
    }, 600);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [navigate]);

  return (
    <div className="relative flex h-full items-center justify-center">
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
