import type { ReactNode } from "react";

/** Compact hero band for inner pages (Products, Features, Pricing, …). */
export function PageHero({
  eyebrow,
  title,
  lead,
  children,
}: {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="relative overflow-hidden border-b border-slate-100">
      <div aria-hidden className="absolute inset-0 -z-10 mesh" />
      <div className="container py-16 text-center sm:py-20">
        {eyebrow && <span className="eyebrow mb-4">{eyebrow}</span>}
        <h1 className="mx-auto max-w-3xl text-4xl font-extrabold leading-[1.1] tracking-tight text-ink sm:text-5xl">
          {title}
        </h1>
        {lead && <p className="lead mx-auto mt-5 max-w-2xl">{lead}</p>}
        {children && <div className="mt-8 flex flex-wrap items-center justify-center gap-3">{children}</div>}
      </div>
    </section>
  );
}
