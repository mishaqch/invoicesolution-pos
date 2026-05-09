/**
 * i18n setup for the POS terminal.
 *
 * - Two locales: en (default) and ur (Urdu, RTL).
 * - Selection persists in localStorage so cashiers don't re-pick on every
 *   shift.
 * - On change, the <html> dir attribute is flipped so Tailwind's `rtl:`
 *   variant takes effect across the app.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en.json";
import ur from "./locales/ur.json";

const STORAGE_KEY = "pos.locale";
type Locale = "en" | "ur";

function getInitialLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "ur") return stored;
  } catch {
    /* localStorage may be unavailable in tests */
  }
  return "en";
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    ur: { translation: ur },
  },
  lng: getInitialLocale(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
});

applyDir(i18n.language as Locale);
i18n.on("languageChanged", (lng) => {
  applyDir(lng as Locale);
  try {
    window.localStorage.setItem(STORAGE_KEY, lng);
  } catch {
    /* swallow */
  }
});

function applyDir(lng: Locale) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = lng;
  document.documentElement.dir = lng === "ur" ? "rtl" : "ltr";
}

export default i18n;
