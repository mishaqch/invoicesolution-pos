import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getModifierGroups } from "@/api/restaurant";
import { fmt } from "@/lib/money";
import type { LineModifier, ModifierGroup, ModifierOption, PosProduct } from "@/types";

interface Props {
  product: PosProduct;
  onConfirm: (product: PosProduct, modifiers: LineModifier[]) => void;
  onClose: () => void;
}

/**
 * Minimal modifier picker — a slide-up sheet reusing the modal scrim visual
 * language. The parent only opens this when a product HAS groups; a product
 * with no groups is added straight to the cart (no sheet). Respects each
 * group's min/max_select for a light validity check.
 */
export function ModifierPickerSheet({ product, onConfirm, onClose }: Props) {
  const groupsQuery = useQuery<ModifierGroup[]>({
    queryKey: ["modifier-groups", product.id],
    queryFn: () => getModifierGroups(product.id),
  });

  const [selected, setSelected] = useState<Record<string, Set<string>>>({});

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const groups = groupsQuery.data ?? [];

  function toggle(group: ModifierGroup, option: ModifierOption) {
    setSelected((prev) => {
      const cur = new Set(prev[group.id] ?? []);
      if (cur.has(option.id)) {
        cur.delete(option.id);
      } else {
        // Enforce max_select: single-select groups replace, multi grow to cap.
        if (group.max_select === 1) {
          cur.clear();
          cur.add(option.id);
        } else if (group.max_select <= 0 || cur.size < group.max_select) {
          cur.add(option.id);
        }
      }
      return { ...prev, [group.id]: cur };
    });
  }

  function confirm() {
    const mods: LineModifier[] = [];
    for (const g of groups) {
      const ids = selected[g.id] ?? new Set<string>();
      for (const opt of g.modifiers) {
        if (ids.has(opt.id)) {
          mods.push({ name: opt.name, price_delta: opt.price_delta });
        }
      }
    }
    onConfirm(product, mods);
  }

  const unmetRequired = groups.some((g) => {
    const count = (selected[g.id] ?? new Set()).size;
    return g.min_select > 0 && count < g.min_select;
  });

  return (
    <div
      className="modal-scrim"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="mod-title">
        <div className="modal-head">
          <div>
            <h2 id="mod-title">{product.name}</h2>
            <p>Choose options for this dish.</p>
          </div>
          <button className="modal-x" type="button" aria-label="Close" onClick={onClose} />
        </div>

        <div className="table-grid" style={{ gridTemplateColumns: "1fr", gap: 16 }}>
          {groupsQuery.isLoading ? (
            <div style={{ display: "grid", placeItems: "center", padding: 24 }}>
              <div className="page-spin" role="status" aria-label="Loading options" />
            </div>
          ) : (
            groups.map((g) => (
              <fieldset key={g.id} style={{ border: 0, margin: 0, padding: 0 }}>
                <legend className="field-label">
                  {g.name}
                  {g.min_select > 0 ? " (required)" : ""}
                </legend>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {g.modifiers
                    .filter((o) => o.is_active)
                    .map((o) => {
                      const on = (selected[g.id] ?? new Set()).has(o.id);
                      const delta = Number(o.price_delta);
                      return (
                        <button
                          key={o.id}
                          type="button"
                          className="zone-tabs-opt"
                          aria-pressed={on}
                          onClick={() => toggle(g, o)}
                          style={{
                            appearance: "none",
                            cursor: "pointer",
                            fontFamily: "inherit",
                            fontSize: 13,
                            fontWeight: 700,
                            padding: "10px 14px",
                            borderRadius: 12,
                            border: on ? "2px solid var(--lake)" : "1px solid var(--line)",
                            background: on ? "var(--lake-mist)" : "var(--card-2)",
                            color: on ? "var(--lake)" : "var(--ink)",
                          }}
                        >
                          {o.name}
                          {delta ? ` · +Rs ${fmt(delta)}` : ""}
                        </button>
                      );
                    })}
                </div>
              </fieldset>
            ))
          )}
        </div>

        <div className="modal-foot" style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button className="btn2" type="button" onClick={onClose} style={{ flex: "0 0 auto", minWidth: 110 }}>
            Cancel
          </button>
          <button
            className="auth-btn"
            type="button"
            style={{ margin: 0, width: "auto", minWidth: 160 }}
            disabled={unmetRequired}
            onClick={confirm}
          >
            Add to order
          </button>
        </div>
      </div>
    </div>
  );
}
