interface Props {
  title: string;
  count: number;
  search: string;
  onSearch: (q: string) => void;
}

/** Sticky menu header: category title + dish count + a growing search field. */
export function MenuHeader({ title, count, search, onSearch }: Props) {
  return (
    <div className="menu-head">
      <div className="htxt">
        <h2>{title}</h2>
        <div className="count">
          {count} {count === 1 ? "dish" : "dishes"}
        </div>
      </div>
      <label className="search">
        <span aria-hidden="true">🔍</span>
        <input
          type="search"
          placeholder="Search the menu…"
          aria-label="Search menu"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
        />
      </label>
    </div>
  );
}
