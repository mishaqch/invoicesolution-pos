import type { MenuCategory } from "@/lib/useMenu";

interface Props {
  categories: MenuCategory[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

/** Vertical (landscape) / horizontal (portrait) category rail. */
export function CategoryRail({ categories, activeId, onSelect }: Props) {
  return (
    <nav className="rail" aria-label="Menu categories">
      {categories.map((c) => {
        const active = c.id === activeId;
        return (
          <button
            key={c.id}
            type="button"
            className={"cat" + (active ? " active" : "")}
            aria-current={active ? "true" : undefined}
            onClick={() => onSelect(c.id)}
          >
            <span className="ico" aria-hidden="true">
              {c.icon}
            </span>
            <span className="nm">{c.name.replace(" (Seasonal)", "")}</span>
          </button>
        );
      })}
    </nav>
  );
}
