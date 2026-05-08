import { cn } from "@/lib/utils";

interface PinDotsProps {
  length: number;        // pin entered so far
  capacity?: number;     // total slots
  className?: string;
}

export function PinDots({ length, capacity = 6, className }: PinDotsProps) {
  return (
    <div className={cn("flex items-center justify-center gap-3", className)}>
      {Array.from({ length: capacity }).map((_, i) => {
        const filled = i < length;
        return (
          <div
            key={i}
            className={cn(
              "h-3 w-3 rounded-full border-2 transition-transform",
              filled
                ? "scale-110 border-primary bg-primary"
                : "border-muted-foreground/40 bg-transparent",
            )}
          />
        );
      })}
    </div>
  );
}
