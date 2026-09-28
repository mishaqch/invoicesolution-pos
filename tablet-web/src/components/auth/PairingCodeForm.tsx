import { useState, type FormEvent } from "react";

interface Props {
  onSubmit: (code: string) => void;
  submitting: boolean;
  error: string | null;
}

/** The one-time pairing-code entry (6+ char code from the admin). */
export function PairingCodeForm({ onSubmit, submitting, error }: Props) {
  const [code, setCode] = useState("");
  const trimmed = code.trim();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!trimmed || submitting) return;
    onSubmit(trimmed);
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <label className="field-label" htmlFor="pairing-code">
        Pairing code
      </label>
      <input
        id="pairing-code"
        className="field-input code"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        placeholder="XXXXXX"
        autoComplete="one-time-code"
        autoCapitalize="characters"
        spellCheck={false}
        inputMode="text"
        autoFocus
        aria-describedby={error ? "pairing-error" : undefined}
        aria-invalid={error ? true : undefined}
      />
      {error ? (
        <div className="auth-err" id="pairing-error" role="alert">
          {error}
        </div>
      ) : null}
      <button className="auth-btn" type="submit" disabled={!trimmed || submitting}>
        {submitting ? <span className="spin" aria-hidden="true" /> : null}
        {submitting ? "Pairing…" : "Pair this tablet"}
      </button>
    </form>
  );
}
