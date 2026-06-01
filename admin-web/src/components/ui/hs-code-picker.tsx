/**
 * HsCodePicker — typeahead over the PRAL HS-code catalog.
 *
 * Backed by the existing GET /api/catalog/hs-codes/?search=<q> endpoint
 * (DRF SearchFilter on code + description). Debounces user input so we
 * don't hammer the API on every keystroke. Catalog has ~8,000 codes
 * so client-side filtering isn't viable.
 *
 * Why a custom component instead of `<select>`:
 *   - Stock <select> can't render 8,000 options performantly
 *   - We need text+code search ("rice", "1006", "Basmati")
 *   - We want to display the description alongside the code so the
 *     operator picks the right one (1006.3010 = Basmati vs 1006.3090 = Other)
 *
 * Usage:
 *   <HsCodePicker
 *     value={form.hs_code}
 *     onChange={(code) => setForm({ ...form, hs_code: code })}
 *     required
 *   />
 */
import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { useHsCodes } from "@/lib/queries";
import { cn } from "@/lib/utils";

interface HsCodePickerProps {
  value: string;
  onChange: (code: string) => void;
  required?: boolean;
  disabled?: boolean;
  id?: string;
  placeholder?: string;
  className?: string;
}

export function HsCodePicker({
  value,
  onChange,
  required,
  disabled,
  id,
  placeholder = "Search HS code or description…",
  className,
}: HsCodePickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // Debounce the search by 200ms so we don't fire a request on every
  // keystroke. 200ms is short enough that the typeahead feels live.
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(query), 200);
    return () => window.clearTimeout(t);
  }, [query]);

  const { data, isFetching } = useHsCodes(debounced);
  const results = data?.results ?? [];

  // Close on outside click / Escape.
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
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

  function pick(code: string) {
    onChange(code);
    setOpen(false);
    setQuery("");
  }

  return (
    <div ref={ref} className={cn("relative", className)}>
      {/* Display field — shows the currently-selected code, or a
          "(none)" placeholder if empty. Clicking opens the picker. */}
      <button
        type="button"
        id={id}
        disabled={disabled}
        onClick={() => !disabled && setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          "disabled:cursor-not-allowed disabled:opacity-50",
          !value && required && "border-amber-400",
        )}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-required={required}
      >
        <span className={cn("truncate font-mono", !value && "text-muted-foreground")}>
          {value || "— pick HS code —"}
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
                placeholder={placeholder}
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

          <div
            role="listbox"
            className="max-h-64 overflow-y-auto"
            aria-busy={isFetching}
          >
            {isFetching && results.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">Searching…</p>
            ) : results.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                {debounced
                  ? `No HS codes match "${debounced}".`
                  : "Start typing to search the ~7,900-code PRAL catalog."}
              </p>
            ) : (
              results.map((h) => (
                <button
                  key={h.code}
                  type="button"
                  role="option"
                  aria-selected={h.code === value}
                  onClick={() => pick(h.code)}
                  className={cn(
                    "block w-full px-3 py-2 text-left text-sm hover:bg-muted",
                    h.code === value && "bg-muted",
                  )}
                >
                  <div className="font-mono text-xs font-semibold">{h.code}</div>
                  <div className="text-xs text-muted-foreground line-clamp-1">
                    {h.description}
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
