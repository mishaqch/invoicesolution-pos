/**
 * SearchableSelect — a typeahead dropdown over a CLIENT-SIDE option list.
 *
 * For lists already in memory (products, customers, …) that are too long to
 * scan in a plain <select> but small enough not to need a server search. For
 * server-backed catalogs (8k HS codes) use HsCodePicker instead; this shares
 * its look/behaviour (popover + search box + keyboard nav + outside-click /
 * Escape close) so the two feel identical.
 *
 * Usage:
 *   <SearchableSelect
 *     id="sw-product"
 *     value={product}
 *     onChange={setProduct}
 *     options={products.map((p) => ({ value: p.id, label: `${p.name} (${p.sku})`, keywords: p.sku }))}
 *     placeholder="Search product…"
 *     required
 *   />
 */
import { ChevronDown, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface SearchableOption {
  value: string;
  /** The visible text, also the primary search target. */
  label: string;
  /** Extra text to match on (e.g. SKU, barcode) without showing it as the label. */
  keywords?: string;
  /** Optional muted second line under the label. */
  hint?: string;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: SearchableOption[];
  id?: string;
  required?: boolean;
  disabled?: boolean;
  /** Placeholder for the search box. */
  placeholder?: string;
  /** Text shown on the trigger when nothing is selected. */
  triggerPlaceholder?: string;
  className?: string;
}

export function SearchableSelect({
  value,
  onChange,
  options,
  id,
  required,
  disabled,
  placeholder = "Search…",
  triggerPlaceholder = "— Select —",
  className,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0); // highlighted index for keyboard nav
  const ref = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(
      (o) =>
        o.label.toLowerCase().includes(q) ||
        (o.keywords ?? "").toLowerCase().includes(q),
    );
  }, [options, query]);

  // Keep the active index in range as the filtered list changes.
  useEffect(() => { setActive(0); }, [query, open]);

  // Close on outside click / Escape.
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

  function pick(v: string) {
    onChange(v);
    setOpen(false);
    setQuery("");
  }

  function onSearchKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const opt = filtered[active];
      if (opt) pick(opt.value);
    }
  }

  // Scroll the active option into view as the user arrows through.
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${active}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

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
          !value && required && "border-amber-400",
        )}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-required={required}
      >
        <span className={cn("truncate", !selected && "text-muted-foreground")}>
          {selected ? selected.label : triggerPlaceholder}
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
                onKeyDown={onSearchKeyDown}
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

          <div ref={listRef} role="listbox" className="max-h-64 overflow-y-auto">
            {filtered.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                {query ? `No matches for "${query}".` : "No options."}
              </p>
            ) : (
              filtered.map((o, i) => (
                <button
                  key={o.value}
                  type="button"
                  role="option"
                  data-idx={i}
                  aria-selected={o.value === value}
                  onClick={() => pick(o.value)}
                  onMouseEnter={() => setActive(i)}
                  className={cn(
                    "block w-full px-3 py-2 text-left text-sm hover:bg-muted",
                    i === active && "bg-muted",
                    o.value === value && "font-medium",
                  )}
                >
                  <div className="truncate">{o.label}</div>
                  {o.hint && (
                    <div className="truncate text-xs text-muted-foreground">{o.hint}</div>
                  )}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
