import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** A page section with consistent vertical rhythm + container. */
export function Section({
  children,
  className,
  containerClassName,
  id,
}: {
  children: ReactNode;
  className?: string;
  containerClassName?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn("section", className)}>
      <div className={cn("container", containerClassName)}>{children}</div>
    </section>
  );
}

/** Centered eyebrow + heading + optional lead, reused at the top of sections. */
export function SectionHeading({
  eyebrow,
  title,
  lead,
  center = true,
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  lead?: ReactNode;
  center?: boolean;
  className?: string;
}) {
  return (
    <div className={cn(center && "mx-auto max-w-2xl text-center", "mb-12", className)}>
      {eyebrow && <span className="eyebrow mb-4">{eyebrow}</span>}
      <h2 className="h2">{title}</h2>
      {lead && <p className="lead mt-4">{lead}</p>}
    </div>
  );
}
