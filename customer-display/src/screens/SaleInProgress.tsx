interface SaleLine {
  name: string;
  qty: string;
  total: string;
}

interface Props {
  lines: SaleLine[];
  total: string;
  business: string;
}

/**
 * Sale-in-progress view — live cart preview the customer sees while the
 * cashier rings up. New lines slide in from the right (CSS animation).
 */
export default function SaleInProgress({ lines, total, business }: Props) {
  return (
    <div className="flex h-screen w-screen flex-col bg-slate-900 p-12">
      <header className="mb-6 flex items-baseline justify-between">
        <h1 className="text-4xl font-light tracking-tight">{business}</h1>
        <span className="text-xl text-slate-400">Your purchase</span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <ul className="space-y-2">
          {lines.length === 0 ? (
            <li className="text-2xl text-slate-500">Cart is empty</li>
          ) : (
            lines.map((line, idx) => (
              <li
                key={idx}
                className="flex animate-[slideIn_300ms_ease-out] items-baseline justify-between border-b border-slate-800 py-3 text-2xl"
              >
                <span className="flex-1">{line.name}</span>
                <span className="w-24 text-right text-slate-400">×{line.qty}</span>
                <span className="w-40 text-right font-mono">Rs. {line.total}</span>
              </li>
            ))
          )}
        </ul>
      </div>

      <footer className="border-t border-slate-700 pt-6">
        <div className="flex items-baseline justify-between">
          <span className="text-3xl text-slate-300">Total</span>
          <span className="font-mono text-6xl font-light">Rs. {total}</span>
        </div>
      </footer>

      <style>{`
        @keyframes slideIn {
          from { transform: translateX(20px); opacity: 0 }
          to   { transform: translateX(0);     opacity: 1 }
        }
      `}</style>
    </div>
  );
}
