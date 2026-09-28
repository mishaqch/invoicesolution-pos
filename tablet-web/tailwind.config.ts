import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * The tablet's visual identity is the TDCP "Lakeside" palette, expressed as
 * raw CSS custom properties in src/index.css (ported 1:1 from the design
 * artifact). Most of the UI is styled with those variables directly through
 * hand-written classes, so this Tailwind config only needs to expose the
 * brand tokens as utilities and register the fonts + radii.
 */
const config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        lake: "var(--lake)",
        "lake-deep": "var(--lake-deep)",
        "lake-mist": "var(--lake-mist)",
        saffron: "var(--saffron)",
        accent: "var(--accent)",
        "accent-soft": "var(--accent-soft)",
        limestone: "var(--limestone)",
        card: "var(--card)",
        "card-2": "var(--card-2)",
        ink: "var(--ink)",
        reed: "var(--reed)",
        line: "var(--line)",
        ring: "var(--ring)",
        ok: "var(--ok)",
        "ok-soft": "var(--ok-soft)",
        warn: "var(--warn)",
        info: "var(--info)",
        "info-soft": "var(--info-soft)",
      },
      fontFamily: {
        serif: ['"Fraunces"', "Georgia", "serif"],
        sans: ['"Plus Jakarta Sans"', "system-ui", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "var(--radius)",
        sm: "var(--radius-sm)",
      },
    },
  },
  plugins: [animate],
} satisfies Config;

export default config;
