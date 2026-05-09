/**
 * Sale-complete celebration. Auto-dismisses to idle after 4s (handled by
 * the parent App). The check icon scales in via a single CSS animation.
 */
export default function ThankYou() {
  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-6 bg-gradient-to-br from-emerald-900 via-emerald-800 to-slate-900">
      <svg
        viewBox="0 0 64 64"
        width="160"
        height="160"
        className="animate-[pop_500ms_cubic-bezier(0.34,1.56,0.64,1)]"
        aria-hidden
      >
        <circle cx="32" cy="32" r="30" fill="white" />
        <path
          d="M18 33 L28 43 L46 23"
          fill="none"
          stroke="rgb(16 185 129)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <h1 className="text-7xl font-light">Thank you!</h1>
      <p className="text-3xl text-slate-300" dir="rtl">شکریہ</p>

      <style>{`
        @keyframes pop {
          0%   { transform: scale(0); opacity: 0 }
          70%  { transform: scale(1.1) }
          100% { transform: scale(1); opacity: 1 }
        }
      `}</style>
    </div>
  );
}
