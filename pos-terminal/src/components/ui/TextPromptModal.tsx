/**
 * In-app text prompt — a drop-in replacement for window.prompt(), which
 * Electron's renderer does NOT implement (it silently returns null, so any
 * feature built on window.prompt — e.g. "Add note", "Hold label" — appears
 * to do nothing). This renders a real modal and resolves a Promise with the
 * entered string, or null when cancelled.
 *
 * Usage:
 *   const prompt = useTextPrompt();
 *   const note = await prompt({ title: "Kitchen note", initialValue: current });
 *   if (note !== null) updateLine(id, { item_note: note.trim() || null });
 *
 * Mount <TextPromptHost/> ONCE near the app root (it reads the shared store).
 */
import { create } from "zustand";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

interface PromptOptions {
  title: string;
  description?: string;
  placeholder?: string;
  initialValue?: string;
  confirmLabel?: string;
  multiline?: boolean;
}

interface PromptState {
  open: boolean;
  options: PromptOptions | null;
  resolve: ((value: string | null) => void) | null;
  show: (options: PromptOptions) => Promise<string | null>;
  close: (value: string | null) => void;
}

const usePromptStore = create<PromptState>((set, get) => ({
  open: false,
  options: null,
  resolve: null,
  show: (options) =>
    new Promise<string | null>((resolve) => {
      set({ open: true, options, resolve });
    }),
  close: (value) => {
    const { resolve } = get();
    resolve?.(value);
    set({ open: false, options: null, resolve: null });
  },
}));

/** Hook returning a prompt() function that resolves to the entered string or null. */
export function useTextPrompt() {
  return usePromptStore((s) => s.show);
}

/** Mount once at the app root. Renders the active prompt modal. */
export function TextPromptHost() {
  const open = usePromptStore((s) => s.open);
  const options = usePromptStore((s) => s.options);
  const close = usePromptStore((s) => s.close);

  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const areaRef = useRef<HTMLTextAreaElement>(null);

  // Reset the field to the requested initial value each time the modal opens.
  useEffect(() => {
    if (open) {
      setValue(options?.initialValue ?? "");
      // Focus + select after the modal paints.
      const t = window.setTimeout(() => {
        const el = options?.multiline ? areaRef.current : inputRef.current;
        el?.focus();
        el?.select?.();
      }, 30);
      return () => window.clearTimeout(t);
    }
  }, [open, options]);

  if (!open || !options) return null;

  const confirm = () => close(value);
  const cancel = () => close(null);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      onClick={cancel}
      onKeyDown={(e) => {
        if (e.key === "Escape") cancel();
      }}
    >
      <div
        className="w-full max-w-md rounded-lg bg-background p-4 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold">{options.title}</h2>
        {options.description && (
          <p className="mt-1 text-sm text-muted-foreground">{options.description}</p>
        )}

        {options.multiline ? (
          <textarea
            ref={areaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={options.placeholder}
            rows={3}
            className="mt-3 w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        ) : (
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                confirm();
              }
            }}
            placeholder={options.placeholder}
            className="mt-3 h-11 w-full rounded-md border border-input bg-background px-3 text-base outline-none focus:ring-2 focus:ring-ring"
          />
        )}

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={cancel}>
            Cancel
          </Button>
          <Button onClick={confirm}>{options.confirmLabel ?? "Save"}</Button>
        </div>
      </div>
    </div>
  );
}
