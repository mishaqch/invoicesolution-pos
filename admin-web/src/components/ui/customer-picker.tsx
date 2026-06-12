/**
 * CustomerPicker — typeahead over the tenant's customers.
 *
 * Backed by GET /api/customers/?search=<q> (server-side search), so it scales
 * to thousands of customers without loading them all into a <select>. Always
 * offers a "Walk-in (unregistered)" choice that clears the buyer.
 *
 * Mirrors HsCodePicker's UX: a button shows the current selection; clicking
 * opens a search box + results list; debounced; closes on outside click /
 * Escape.
 *
 * Usage:
 *   <CustomerPicker
 *     value={customerId}                 // "" = walk-in
 *     selectedLabel={selectedCustomer?.name}  // shown on the button when set
 *     onChange={(id) => setCustomerId(id)}    // "" clears to walk-in
 *     walkInLabel="Walk-in (unregistered)"
 *     disabled={!!debitContext}
 *   />
 */
import { ChevronDown, Search, UserRound, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { useCustomers, type AdminCustomer } from "@/lib/queries";
import { cn } from "@/lib/utils";

interface CustomerPickerProps {
  /** Selected customer id, or "" for walk-in. */
  value: string;
  /** Display label for the selected customer (the parent has the object). */
  selectedLabel?: string | null;
  /** Fires with the customer id ("" = walk-in) AND the full object (null for
   *  walk-in) so the caller keeps the buyer details for the preview. */
  onChange: (customerId: string, customer: AdminCustomer | null) => void;
  disabled?: boolean;
  id?: string;
  walkInLabel?: string;
  className?: string;
}

export function CustomerPicker({
  value,
  selectedLabel,
  onChange,
  disabled,
  id,
  walkInLabel = "Walk-in (unregistered)",
  className,
}: CustomerPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Debounce the search by 200ms so we don't fire on every keystroke.
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query), 200);
    return () => window.clearTimeout(t);
  }, [query]);

  // Only query once the picker is open (and re-query as the search changes).
  const { data, isFetching } = useCustomers(open ? { search: debounced } : {});
  const results = data?.results ?? [];

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function pick(id_: string, customer: AdminCustomer | null) {
    onChange(id_, customer);
    setOpen(false);
    setQuery("");
  }

  const buttonLabel = value ? (selectedLabel || "Selected customer") : walkInLabel;

  return (
    <div ref={ref} className={cn("relative", className)}>
      <button
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
        )}
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <span className={cn("truncate", !value && "text-muted-foreground")}>
          {buttonLabel}
        </span>
        <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-30 mt-1 max-h-80 overflow-hidden rounded-md border bg-background shadow-lg">
          <div className="border-b p-2">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name, NTN, CNIC or phone…"
                className="pl-8 pr-8"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="absolute right-2 top-2.5 rounded p-0.5 text-muted-foreground hover:bg-muted"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>

          <div role="listbox" className="max-h-64 overflow-y-auto" aria-busy={isFetching}>
            {/* Walk-in (clears the buyer) — always available at the top. */}
            <button
              type="button"
              role="option"
              aria-selected={value === ""}
              onClick={() => pick("", null)}
              className={cn(
                "flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted",
                value === "" && "bg-muted",
              )}
            >
              <UserRound className="h-4 w-4 text-muted-foreground" />
              <span>{walkInLabel}</span>
            </button>

            {isFetching && results.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">Searching…</p>
            ) : results.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                {debounced
                  ? `No customers match "${debounced}".`
                  : "Start typing to search your customers."}
              </p>
            ) : (
              results.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  role="option"
                  aria-selected={c.id === value}
                  onClick={() => pick(c.id, c)}
                  className={cn(
                    "block w-full px-3 py-2 text-left text-sm hover:bg-muted",
                    c.id === value && "bg-muted",
                  )}
                >
                  <div className="font-medium">{c.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {c.ntn
                      ? `NTN ${c.ntn}`
                      : c.cnic
                        ? `CNIC ${c.cnic}`
                        : c.phone
                          ? c.phone
                          : "Unregistered"}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
