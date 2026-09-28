import { Toaster, toast } from "sonner";

/**
 * Sonner toast provider, themed to the Lakeside palette. Mounted once at the
 * app root. The dish-shaped success toasts in the artifact are matched by
 * sonner's default look plus our token colours.
 */
export function ToastProvider() {
  return (
    <Toaster
      position="bottom-center"
      toastOptions={{
        style: {
          background: "var(--ink)",
          color: "var(--limestone)",
          border: "none",
          borderRadius: "14px",
          fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif',
          fontWeight: 700,
          fontSize: "13.5px",
        },
      }}
      // Respect reduced motion — sonner honours the OS setting itself.
      closeButton={false}
      duration={2600}
    />
  );
}

/** Thin re-export so callers import from one place. */
// eslint-disable-next-line react-refresh/only-export-components
export { toast };
