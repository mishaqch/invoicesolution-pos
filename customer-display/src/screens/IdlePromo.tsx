import { useEffect, useState } from "react";

const PROMOS = [
  { headline: "Welcome", subline: "خوش آمدید" },
  { headline: "Quality products at fair prices", subline: "" },
  { headline: "Ask us about delivery", subline: "" },
];

/**
 * Idle promo rotation. Three placeholder slides; replace with admin-uploaded
 * content in V1.5. Crossfade is 600ms.
 */
export default function IdlePromo() {
  const [idx, setIdx] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => setIdx((i) => (i + 1) % PROMOS.length), 6000);
    return () => window.clearInterval(t);
  }, []);
  const promo = PROMOS[idx];
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-gradient-to-br from-slate-900 via-slate-800 to-emerald-950">
      <div key={idx} className="animate-[fadeIn_600ms_ease-out] text-center">
        <h1 className="text-7xl font-light tracking-tight">{promo.headline}</h1>
        {promo.subline && (
          <p className="mt-4 text-3xl text-slate-300" dir="rtl">
            {promo.subline}
          </p>
        )}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity: 0 } to { opacity: 1 } }
      `}</style>
    </div>
  );
}
