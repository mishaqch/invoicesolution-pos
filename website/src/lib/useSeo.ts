import { useEffect } from "react";

/**
 * Minimal per-page SEO without a dependency: set <title>, meta description,
 * and canonical on mount. A marketing SPA is crawled fine by modern bots, and
 * this keeps each route's tab title + description correct on client navigation.
 */
export function useSeo(opts: { title: string; description?: string; path?: string }) {
  useEffect(() => {
    const fullTitle = opts.title.includes("InvoiceSolution")
      ? opts.title
      : `${opts.title} — InvoiceSolution`;
    document.title = fullTitle;

    if (opts.description) {
      let tag = document.querySelector('meta[name="description"]');
      if (!tag) {
        tag = document.createElement("meta");
        tag.setAttribute("name", "description");
        document.head.appendChild(tag);
      }
      tag.setAttribute("content", opts.description);
    }

    if (opts.path) {
      let link = document.querySelector('link[rel="canonical"]');
      if (!link) {
        link = document.createElement("link");
        link.setAttribute("rel", "canonical");
        document.head.appendChild(link);
      }
      link.setAttribute("href", `https://invoicesolution.pk${opts.path}`);
    }
  }, [opts.title, opts.description, opts.path]);
}
