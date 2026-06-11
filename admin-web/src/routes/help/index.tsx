import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Search } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import { ARTICLES, type HelpArticle } from "./content";

export default function HelpCenter() {
  const { slug } = useParams<{ slug?: string }>();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ARTICLES;
    return ARTICLES.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.body.toLowerCase().includes(q) ||
        a.tags.some((t) => t.includes(q)),
    );
  }, [query]);

  const active = slug ? ARTICLES.find((a) => a.slug === slug) : null;

  if (active) {
    return <ArticlePage article={active} onBack={() => navigate("/help")} />;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Help center</h1>
        <p className="text-sm text-muted-foreground">
          Common how-tos and troubleshooting. Type to filter.
        </p>
      </div>

      <div className="relative w-full sm:max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 shrink-0 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search articles…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search help articles"
        />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {matches.map((a) => (
          <button
            type="button"
            key={a.slug}
            onClick={() => navigate(`/help/${a.slug}`)}
            className="text-left"
          >
            <Card className="h-full transition-colors hover:bg-accent">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">{a.title}</CardTitle>
              </CardHeader>
              <CardContent className="text-xs text-muted-foreground">
                {a.summary}
              </CardContent>
            </Card>
          </button>
        ))}
      </div>

      {matches.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No articles match. Try a different keyword.
        </p>
      )}
    </div>
  );
}

function ArticlePage({ article, onBack }: { article: HelpArticle; onBack: () => void }) {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <button
        onClick={onBack}
        className="text-sm text-muted-foreground hover:underline"
      >
        ← Help center
      </button>
      <h1 className="text-2xl font-semibold tracking-tight">{article.title}</h1>
      <article className="prose prose-sm max-w-none dark:prose-invert">
        {article.body.split("\n\n").map((para, idx) => (
          <p key={idx}>{para}</p>
        ))}
      </article>
    </div>
  );
}
