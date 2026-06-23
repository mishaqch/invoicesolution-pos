import type { ReactNode } from "react";

import { PageHero } from "@/components/sections/PageHero";

/** Shared shell + simple prose styling for legal pages. */
export function LegalLayout({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: ReactNode;
}) {
  return (
    <>
      <PageHero eyebrow="Legal" title={title} lead={`Last updated: ${updated}`} />
      <section className="container section">
        <div className="prose-legal mx-auto max-w-3xl space-y-6 text-ink-soft [&_h2]:mb-2 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-ink [&_p]:leading-relaxed [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">
          {children}
        </div>
      </section>
    </>
  );
}
