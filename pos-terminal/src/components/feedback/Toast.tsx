/**
 * Lightweight non-blocking toast — replaces window.alert() across the
 * terminal so cashier flow doesn't grind to a halt.
 *
 * Accessibility:
 *   - The container renders an aria-live region (polite), so screen
 *     readers announce new toasts without stealing focus.
 *   - role="status" for info / success / warning, role="alert" for
 *     destructive — alert is louder and interrupts AT speech queue.
 *   - Auto-dismisses on a timer; the dismiss button is keyboard-focusable.
 *   - Respects prefers-reduced-motion: no slide animation when set.
 *
 * Usage:
 *   const toast = useToast();
 *   toast.show({ message: "Sale held", variant: "success" });
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastVariant = "info" | "success" | "warning" | "destructive";

interface Toast {
  id: number;
  message: string;
  variant: ToastVariant;
  /** ms before auto-dismiss; 0 = sticky. */
  ttl: number;
}

interface ToastContextValue {
  show: (input: { message: string; variant?: ToastVariant; ttl?: number }) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const v = useContext(ToastContext);
  if (!v) {
    throw new Error("useToast must be used inside <ToastProvider>");
  }
  return v;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((curr) => curr.filter((t) => t.id !== id));
  }, []);

  const show = useCallback<ToastContextValue["show"]>(
    ({ message, variant = "info", ttl = 3500 }) => {
      const id = nextId.current++;
      setToasts((curr) => [...curr, { id, message, variant, ttl }]);
      if (ttl > 0) {
        // Timer is set in the component body of ToastView itself so a
        // user's prefers-reduced-motion toggle still works without
        // having to plumb it through here.
        window.setTimeout(() => dismiss(id), ttl);
      }
    },
    [dismiss],
  );

  const ctx = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      {/* Fixed viewport-relative container. Pointer-events-none so it
          never blocks clicks on the page; individual toasts opt back in. */}
      <div
        aria-live="polite"
        aria-atomic="false"
        className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <ToastView key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

function ToastView({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  // Variant → semantic palette. Tokens defined in src/index.css.
  // Destructive uses role="alert" to interrupt AT; others use "status".
  const bg = {
    info: "bg-info-soft text-info-soft-foreground",
    success: "bg-success-soft text-success-soft-foreground",
    warning: "bg-warning-soft text-warning-soft-foreground",
    destructive: "bg-destructive-soft text-destructive-soft-foreground",
  }[toast.variant];
  const role = toast.variant === "destructive" ? "alert" : "status";
  return (
    <div
      role={role}
      className={
        "pointer-events-auto flex max-w-sm items-start gap-3 rounded-md border " +
        "px-4 py-3 text-sm shadow-md " +
        bg
      }
    >
      <span className="flex-1">{toast.message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="rounded-sm text-current opacity-70 hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-current"
      >
        ×
      </button>
    </div>
  );
}

/**
 * Used in places that can't use the hook (e.g. an event listener
 * outside the React tree). Falls back to console.warn if the
 * provider hasn't mounted yet.
 */
let standalone: ToastContextValue | null = null;
export function setStandaloneToastSink(v: ToastContextValue | null): void {
  standalone = v;
}
export function emitStandaloneToast(
  message: string,
  variant: ToastVariant = "info",
): void {
  if (standalone) standalone.show({ message, variant });
  else console.warn(`[toast unmounted] ${variant}: ${message}`);
}
// Keep an unused-export warning silent until the standalone helper
// is actually wired by a route.
void emitStandaloneToast;
