/**
 * Modifier picker — shown when a restaurant menu item has modifier groups
 * (sizes, add-ons). The cashier picks options; their price deltas are summed
 * into the line's unit price and the chosen modifiers are attached for the
 * receipt + KOT. Groups/options are fetched on demand from the server.
 *
 * Required single-choice groups (min=1,max=1) render as radios; optional /
 * multi groups as checkboxes with a max-select guard.
 */

import { useState } from "react";

import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Money, rs } from "@/lib/money";

interface Modifier { id: string; name: string; price_delta: string }
interface Group {
  id: string; name: string; min_select: number; max_select: number; modifiers: Modifier[];
}
export interface ChosenModifiers {
  modifiers: { name: string; price: string }[];
  /** Money delta to ADD to the base unit price. */
  delta: Money;
}

/** Fetch the modifier groups attached to a product. Returns [] when none/offline. */
export async function fetchModifierGroups(productId: string): Promise<Group[]> {
  // Use the shared api() helper (correct base URL + bearer token) instead of a
  // hand-rolled fetch on VITE_API_URL. Returns [] when the item has no groups
  // or the call fails (the picker is then skipped and the item adds directly).
  try {
    const data = await api<{ results?: Group[] } | Group[]>(
      `/restaurant/modifier-groups/?product=${productId}`,
    );
    return (Array.isArray(data) ? data : data.results) ?? [];
  } catch {
    return [];
  }
}

export function ModifierPicker({
  productName,
  groups,
  onCancel,
  onConfirm,
}: {
  productName: string;
  groups: Group[];
  onCancel: () => void;
  onConfirm: (chosen: ChosenModifiers) => void;
}) {
  // selected[groupId] = Set of modifier ids
  const [selected, setSelected] = useState<Record<string, Set<string>>>({});

  function toggle(group: Group, mod: Modifier) {
    setSelected((prev) => {
      const cur = new Set(prev[group.id] ?? []);
      if (group.max_select <= 1) {
        cur.clear();
        cur.add(mod.id);
      } else if (cur.has(mod.id)) {
        cur.delete(mod.id);
      } else if (cur.size < group.max_select) {
        cur.add(mod.id);
      }
      return { ...prev, [group.id]: cur };
    });
  }

  function confirm() {
    const chosen: { name: string; price: string }[] = [];
    let delta = Money.zero();
    for (const g of groups) {
      for (const m of g.modifiers) {
        if (selected[g.id]?.has(m.id)) {
          chosen.push({ name: m.name, price: Money.fromStr(m.price_delta).toStorageString() });
          delta = delta.add(Money.fromStr(m.price_delta));
        }
      }
    }
    onConfirm({ modifiers: chosen, delta });
  }

  // Required groups must have a selection before confirm is enabled.
  const unmetRequired = groups.some((g) => g.min_select > 0 && (selected[g.id]?.size ?? 0) < g.min_select);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onCancel}>
      <div className="w-full max-w-md rounded-lg bg-background p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-semibold">{productName}</h2>
        <div className="mt-3 max-h-[60vh] space-y-4 overflow-auto">
          {groups.map((g) => (
            <div key={g.id}>
              <div className="mb-1.5 text-sm font-medium">
                {g.name}
                <span className="ml-2 text-xs text-muted-foreground">
                  {g.min_select > 0 ? "required" : "optional"}
                  {g.max_select > 1 ? ` · up to ${g.max_select}` : ""}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {g.modifiers.map((m) => {
                  const on = selected[g.id]?.has(m.id) ?? false;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => toggle(g, m)}
                      className={`flex items-center justify-between rounded-md border px-3 py-2 text-sm transition-colors ${
                        on ? "border-primary bg-primary-soft text-primary-soft-foreground" : "hover:bg-accent"
                      }`}
                    >
                      <span>{m.name}</span>
                      {Number(m.price_delta) > 0 && (
                        <span className="font-mono text-xs">+{rs(m.price_delta)}</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onCancel}>Cancel</Button>
          <Button disabled={unmetRequired} onClick={confirm}>Add to order</Button>
        </div>
      </div>
    </div>
  );
}
