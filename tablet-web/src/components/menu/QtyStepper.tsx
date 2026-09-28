interface Props {
  qty: number;
  onInc: (e: React.MouseEvent) => void;
  onDec: (e: React.MouseEvent) => void;
  label: string;
}

/** The − count + control that the "+" morphs into once an item is on the
 *  order (menu-card variant). Matches the artifact's .stepper markup. */
export function QtyStepper({ qty, onInc, onDec, label }: Props) {
  return (
    <div className={"stepper" + (qty === 1 ? " one" : "")} role="group" aria-label={`${label} quantity`}>
      <button
        type="button"
        className="minus"
        aria-label={qty === 1 ? `Remove ${label}` : `Remove one ${label}`}
        onClick={onDec}
      />
      <span className="sq" aria-live="polite">
        {qty}
      </span>
      <button type="button" className="plus" aria-label={`Add one ${label}`} onClick={onInc} />
    </div>
  );
}
