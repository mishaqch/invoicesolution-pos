import { Delete, X } from "lucide-react";

interface PinKeypadProps {
  onDigit: (d: string) => void;
  onBackspace: () => void;
  onClear: () => void;
  disabled?: boolean;
}

const ROWS = ["1 2 3", "4 5 6", "7 8 9"].map((r) => r.split(" "));

export function PinKeypad({ onDigit, onBackspace, onClear, disabled }: PinKeypadProps) {
  return (
    <div className="mx-auto grid w-full max-w-xs grid-cols-3 gap-3">
      {ROWS.flat().map((d) => (
        <KeypadButton key={d} onClick={() => onDigit(d)} disabled={disabled}>
          {d}
        </KeypadButton>
      ))}
      <KeypadButton onClick={onClear} disabled={disabled} variant="muted" aria-label="Clear">
        <X className="h-5 w-5" />
      </KeypadButton>
      <KeypadButton onClick={() => onDigit("0")} disabled={disabled}>
        0
      </KeypadButton>
      <KeypadButton
        onClick={onBackspace}
        disabled={disabled}
        variant="muted"
        aria-label="Backspace"
      >
        <Delete className="h-5 w-5" />
      </KeypadButton>
    </div>
  );
}

function KeypadButton({
  children,
  onClick,
  disabled,
  variant = "default",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "muted" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        "flex h-16 items-center justify-center rounded-xl text-2xl font-medium " +
        "transition-transform active:scale-95 focus-visible:outline-none focus-visible:ring-2 " +
        "focus-visible:ring-ring disabled:opacity-50 " +
        (variant === "default"
          ? "bg-muted hover:bg-muted/80 text-foreground"
          : "bg-transparent hover:bg-muted/60 text-muted-foreground")
      }
      {...rest}
    >
      {children}
    </button>
  );
}
