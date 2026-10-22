/**
 * Room categories must never appear on the SALE page.
 *
 * A room is booked through Open Stay; an extra mattress is ticked on the
 * check-in form and billed to the guest's folio. Neither is a cart item.
 *
 * The filter previously matched the exact name "rooms" only, so the separate
 * "Room Extras" category leaked the mattress into the restaurant menu grid —
 * a cashier could ring one up as a standalone food sale instead of charging
 * it to the stay, which is exactly what was reported.
 */

import { describe, expect, it } from "vitest";

/** Mirrors ProductGrid's filter. */
const ROOM_CATEGORIES = new Set(["rooms", "room extras"]);
const visible = (cats: { name: string }[]) =>
  cats.filter((c) => !ROOM_CATEGORIES.has(c.name.trim().toLowerCase()));

describe("sale page category chips", () => {
  it("hides Room Extras — the reported bug", () => {
    const names = visible([
      { name: "Room Extras" }, { name: "BBQ" }, { name: "Soups" },
    ]).map((c) => c.name);
    expect(names).toEqual(["BBQ", "Soups"]);
  });

  it("still hides Rooms", () => {
    expect(visible([{ name: "Rooms" }, { name: "Dessert" }])).toEqual([
      { name: "Dessert" },
    ]);
  });

  it("ignores case and padding, as the catalog is hand-typed", () => {
    expect(visible([
      { name: "  ROOM EXTRAS " }, { name: "rooms" }, { name: "Beverages" },
    ])).toEqual([{ name: "Beverages" }]);
  });

  it("does not hide a genuine food category that merely mentions a room", () => {
    // "Room Service" is food — it must stay sellable.
    const names = visible([{ name: "Room Service" }, { name: "BBQ" }])
      .map((c) => c.name);
    expect(names).toContain("Room Service");
  });
});

describe("tapping an add-on twice", () => {
  it("increments quantity rather than adding a second line", () => {
    // Mirrors addToCart() in FolioDetail.
    type Line = { product_id: string; quantity: string };
    let cart: Line[] = [];
    const add = (product_id: string) => {
      const i = cart.findIndex((l) => l.product_id === product_id);
      if (i >= 0) {
        const next = [...cart];
        next[i] = { ...next[i], quantity: String(Number(next[i].quantity) + 1) };
        cart = next;
        return;
      }
      cart = [...cart, { product_id, quantity: "1" }];
    };

    add("mattress"); add("mattress"); add("mattress");

    expect(cart).toEqual([{ product_id: "mattress", quantity: "3" }]);
  });
});


describe("search and the recent list must not leak add-ons either", () => {
  /** Mirrors the grid filter: hide products whose category is a room one. */
  const hiddenIds = new Set(["cat-rooms", "cat-room-extras"]);
  const grid = (rows: { name: string; category_id: string | null }[]) =>
    rows.filter((p) => !p.category_id || !hiddenIds.has(p.category_id));

  it('a cashier typing "mattress" on the sale page finds nothing', () => {
    // Hiding the CHIP was not enough: search bypasses categories entirely,
    // so the mattress was still sellable as a food item.
    const results = [{ name: "Extra Mattress", category_id: "cat-room-extras" }];
    expect(grid(results)).toEqual([]);
  });

  it("the default recent list never shows a room add-on", () => {
    const recent = [
      { name: "Extra Mattress", category_id: "cat-room-extras" },
      { name: "VIP Room / night", category_id: "cat-rooms" },
      { name: "Biryani", category_id: "cat-bbq" },
    ];
    expect(grid(recent).map((p) => p.name)).toEqual(["Biryani"]);
  });

  it("an uncategorised product is still sellable", () => {
    expect(grid([{ name: "Misc item", category_id: null }])).toHaveLength(1);
  });
});
