/**
 * Presentation-only emoji glyphs for dishes + categories, ported from the
 * artifact's glyph() map. The real menu comes from the server (which has no
 * emoji), so we derive a plate glyph and a veg marker from the item name.
 * Nothing here affects money, tax, or the order payload.
 */

const DISH_MAP: Array<[string, string]> = [
  ["fish", "🐟"],
  ["biryani", "🍚"],
  ["rice", "🍚"],
  ["noodle", "🍜"],
  ["chowmein", "🍜"],
  ["soup", "🍲"],
  ["yakhni", "🍲"],
  ["naan", "🫓"],
  ["roti", "🫓"],
  ["salad", "🥗"],
  ["raita", "🥣"],
  ["kachumber", "🥗"],
  ["lime", "🍹"],
  ["chai", "🍵"],
  ["patti", "🍵"],
  ["water", "💧"],
  ["drink", "🥤"],
  ["halwa", "🍮"],
  ["kheer", "🍚"],
  ["falooda", "🍨"],
  ["trifle", "🍨"],
  ["puri", "🥘"],
  ["paratha", "🥞"],
  ["omelette", "🍳"],
  ["nihari", "🍲"],
  ["daal", "🍛"],
  ["korma", "🍛"],
  ["handi", "🍲"],
  ["karahi", "🍲"],
  ["seekh", "🍢"],
  ["tikka", "🍗"],
  ["boti", "🍗"],
  ["malai", "🍗"],
  ["chicken", "🍗"],
  ["kabab", "🍢"],
  ["room", "🛏️"],
  ["suite", "🛏️"],
  ["cheese", "🧀"],
  ["manchurian", "🍲"],
  ["shashlik", "🍢"],
];

export function glyphFor(name: string): string {
  const n = name.toLowerCase();
  for (const [k, g] of DISH_MAP) if (n.includes(k)) return g;
  return "🍽️";
}

/** Rough veg/non-veg marker from the name (chicken/fish/meat -> non-veg). */
const NONVEG = ["chicken", "fish", "mutton", "beef", "kabab", "boti", "tikka", "seekh", "nihari", "meat", "shashlik", "prawn"];
export function vegFor(name: string): "g" | "n" {
  const n = name.toLowerCase();
  return NONVEG.some((k) => n.includes(k)) ? "n" : "g";
}

/** Category-name -> rail icon, ported from the artifact's MENU icons. */
const CAT_MAP: Array<[string, string]> = [
  ["b.b.q", "🔥"],
  ["bbq", "🔥"],
  ["barbeque", "🔥"],
  ["pakistani", "🍛"],
  ["rice", "🍚"],
  ["chinese", "🥢"],
  ["soup", "🍲"],
  ["fish", "🐟"],
  ["tandoor", "🫓"],
  ["bread", "🫓"],
  ["salad", "🥗"],
  ["beverage", "🥤"],
  ["drink", "🥤"],
  ["dessert", "🍮"],
  ["sweet", "🍮"],
  ["breakfast", "🍳"],
  ["starter", "🍢"],
  ["appetiz", "🍢"],
];

export function categoryIcon(name: string, fallbackIcon?: string | null): string {
  if (fallbackIcon && fallbackIcon.trim()) return fallbackIcon;
  const n = name.toLowerCase();
  for (const [k, g] of CAT_MAP) if (n.includes(k)) return g;
  return "🍽️";
}
