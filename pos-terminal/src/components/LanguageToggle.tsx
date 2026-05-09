import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";

/**
 * Compact en/ur switcher. The label is shown in the OPPOSITE language so
 * a cashier looking at an English UI sees "اردو" and vice versa — no
 * translation needed to know how to switch back.
 */
export function LanguageToggle() {
  const { i18n } = useTranslation();
  const current = i18n.language;
  const next = current === "ur" ? "en" : "ur";

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => void i18n.changeLanguage(next)}
      aria-label={`Switch to ${next === "ur" ? "Urdu" : "English"}`}
    >
      {next === "ur" ? "اردو" : "English"}
    </Button>
  );
}
