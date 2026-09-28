import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { syncCatalog } from "@/api/catalog";
import { categoryIcon } from "@/lib/menu-glyph";
import type { Category, CatalogSyncResponse, PosProduct } from "@/types";

export interface MenuCategory {
  id: string;
  name: string;
  icon: string;
  products: PosProduct[];
}

export interface Menu {
  categories: MenuCategory[];
  /** Products with no category, grouped under a synthetic "Other". */
  hasProducts: boolean;
}

// NB: the "Rooms" category is a ROOM folio category handled at reception, NOT a
// food category — a waiter's tablet takes RESTAURANT orders only. We exclude it
// by NAME on the client. This couples the client to the exact category name;
// if the admin renames "Rooms", update this constant.
const EXCLUDED_CATEGORY_NAME = "Rooms";

/** Fetch the catalog and shape it into ordered categories with their products,
 *  excluding inactive/deleted items and the Rooms category. */
export function useMenu() {
  const query = useQuery<CatalogSyncResponse>({
    queryKey: ["catalog-sync"],
    queryFn: () => syncCatalog(),
    staleTime: 60_000,
  });

  const menu = useMemo<Menu>(() => {
    const data = query.data;
    if (!data) return { categories: [], hasProducts: false };

    const activeCats = data.categories
      .filter((c: Category) => c.is_active && c.name !== EXCLUDED_CATEGORY_NAME)
      .sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));

    const excludedIds = new Set(
      data.categories.filter((c) => c.name === EXCLUDED_CATEGORY_NAME).map((c) => c.id),
    );

    const byCat = new Map<string, PosProduct[]>();
    for (const p of data.products) {
      if (!p.is_active || p.deleted_at) continue;
      if (p.category && excludedIds.has(p.category)) continue; // drop Rooms items
      const key = p.category ?? "__uncat__";
      const arr = byCat.get(key) ?? [];
      arr.push(p);
      byCat.set(key, arr);
    }

    const categories: MenuCategory[] = [];
    for (const c of activeCats) {
      const products = (byCat.get(c.id) ?? []).sort((a, b) => a.name.localeCompare(b.name));
      if (products.length === 0) continue; // hide empty categories
      categories.push({ id: c.id, name: c.name, icon: categoryIcon(c.name, c.icon), products });
    }
    // Uncategorised products (excluding Rooms) go under a synthetic bucket.
    const uncat = byCat.get("__uncat__") ?? [];
    if (uncat.length) {
      categories.push({
        id: "__uncat__",
        name: "Other",
        icon: "🍽️",
        products: uncat.sort((a, b) => a.name.localeCompare(b.name)),
      });
    }

    return { categories, hasProducts: data.products.length > 0 };
  }, [query.data]);

  return { ...query, menu };
}
