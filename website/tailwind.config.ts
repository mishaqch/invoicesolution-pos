import type { Config } from "tailwindcss";

/**
 * Marketing-site theme. Brand palette is the SAME emerald the app uses
 * (Pakistan-flag green) so the site → app handoff feels like one product.
 * We use plain hex/Tailwind scales here (no CSS-var theming) — a marketing
 * site is light-only and doesn't need the app's runtime re-theming.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: "1.25rem", lg: "2rem" },
      screens: { "2xl": "1200px" },
    },
    extend: {
      colors: {
        // Emerald brand ramp (matches admin-web --primary: 142 71% 36%).
        brand: {
          50: "#ecfdf5",
          100: "#d1fae5",
          200: "#a7f3d0",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#10b981",
          600: "#16a34a", // primary (app emerald-600)
          700: "#15803d",
          800: "#166534",
          900: "#14532d",
        },
        ink: {
          DEFAULT: "#0f172a", // slate-900 — primary text
          soft: "#334155", // slate-700 — body
          muted: "#64748b", // slate-500 — secondary
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      borderRadius: {
        lg: "0.75rem",
        xl: "1rem",
        "2xl": "1.25rem",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px rgba(15,23,42,0.06)",
        glow: "0 10px 40px -12px rgba(22,163,74,0.45)",
        card: "0 1px 3px rgba(15,23,42,0.06), 0 12px 32px -8px rgba(15,23,42,0.10)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(to right, rgba(15,23,42,0.04) 1px, transparent 1px), linear-gradient(to bottom, rgba(15,23,42,0.04) 1px, transparent 1px)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-10px)" },
        },
        marquee: {
          from: { transform: "translateX(0)" },
          to: { transform: "translateX(-50%)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.4" },
        },
      },
      animation: {
        float: "float 6s ease-in-out infinite",
        marquee: "marquee 28s linear infinite",
        "pulse-dot": "pulse-dot 1.6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
