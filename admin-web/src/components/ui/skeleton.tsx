import { cn } from "@/lib/utils";

/**
 * Skeleton — placeholder bar shown while data is loading.
 *
 * Compose sizes via Tailwind utilities, e.g.:
 *   <Skeleton className="h-4 w-32" />     // a single line
 *   <Skeleton className="h-10 w-full" />  // a button placeholder
 *
 * Respects prefers-reduced-motion (animation killed globally).
 */
export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn(
        "animate-pulse rounded-md bg-muted",
        className,
      )}
      {...props}
    />
  );
}
