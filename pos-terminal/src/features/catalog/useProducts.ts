import { useEffect, useState } from "react";

import type { PosProductSqliteRow } from "../../../electron/preload";

const DEBOUNCE_MS = 200;

export function useProductSearch(query: string) {
  const [results, setResults] = useState<PosProductSqliteRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const handle = window.setTimeout(async () => {
      setLoading(true);
      try {
        const rows = query.trim()
          ? await window.api.catalog.search(query, 50)
          : await window.api.catalog.list(50);
        if (!cancelled) setResults(rows);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [query]);

  return { results, loading };
}
