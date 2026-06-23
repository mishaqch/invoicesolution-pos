import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, BadgeCheck, ShieldCheck, WifiOff } from "lucide-react";

import { ButtonLink } from "@/components/ui/Button";
import { ReceiptMock } from "@/components/sections/ReceiptMock";
import { cn } from "@/lib/cn";

export function Hero() {
  const reduce = useReducedMotion();
  const rise = (delay: number) =>
    reduce
      ? {}
      : {
          initial: { opacity: 0, y: 20 },
          animate: { opacity: 1, y: 0 },
          transition: { duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] as const },
        };

  return (
    <section className="relative overflow-hidden">
      {/* Background: faint grid + gradient mesh */}
      <div aria-hidden className="absolute inset-0 -z-10 mesh" />
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-grid-faint bg-[size:44px_44px] [mask-image:radial-gradient(70%_60%_at_50%_0%,black,transparent)]"
      />

      <div className="container grid items-center gap-14 pb-16 pt-14 sm:pt-20 lg:grid-cols-2 lg:gap-8 lg:pb-24 lg:pt-24">
        <div>
          <motion.div {...rise(0)}>
            <span className="eyebrow">
              <BadgeCheck className="h-3.5 w-3.5" /> FBR Digital Invoicing
            </span>
          </motion.div>

          <motion.h1 {...rise(0.06)} className="h1 mt-5">
            Run your shop.{" "}
            <span className="relative whitespace-nowrap text-brand-600">
              Stay FBR-compliant.
            </span>{" "}
            Even offline.
          </motion.h1>

          <motion.p {...rise(0.12)} className="lead mt-5 max-w-xl">
            InvoiceSolution is the FBR-compliant POS &amp; Digital Invoicing system built for
            Pakistani businesses. Real FBR invoice numbers, scannable QR receipts, and software
            that keeps selling when your internet doesn&rsquo;t.
          </motion.p>

          <motion.div {...rise(0.18)} className="mt-8 flex flex-wrap items-center gap-3">
            <ButtonLink to="/contact" size="lg">
              Book a free demo <ArrowRight className="h-4 w-4" />
            </ButtonLink>
            <ButtonLink to="/pricing" variant="secondary" size="lg">
              See pricing
            </ButtonLink>
          </motion.div>

          <motion.div
            {...rise(0.26)}
            className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-ink-muted"
          >
            <span className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-brand-600" /> Real FBR invoice numbers
            </span>
            <span className="flex items-center gap-2">
              <WifiOff className="h-4 w-4 text-brand-600" /> Works offline
            </span>
            <span className="flex items-center gap-2">
              <BadgeCheck className="h-4 w-4 text-brand-600" /> 14-day trial
            </span>
          </motion.div>
        </div>

        {/* Hero visual */}
        <motion.div
          {...(reduce
            ? {}
            : {
                initial: { opacity: 0, scale: 0.96, y: 24 },
                animate: { opacity: 1, scale: 1, y: 0 },
                transition: { duration: 0.7, delay: 0.15, ease: [0.22, 1, 0.36, 1] as const },
              })}
          className="relative mx-auto w-full max-w-md lg:max-w-none"
        >
          <div className={cn("relative", !reduce && "animate-float")}>
            <ReceiptMock />
          </div>
          {/* Floating stat chips */}
          <FloatChip className="-left-2 top-8 sm:-left-6" delay={0.5} reduce={reduce}>
            <span className="text-xs font-medium text-ink-muted">Today&rsquo;s sales</span>
            <span className="text-lg font-bold text-ink">Rs 84,250.00</span>
          </FloatChip>
          <FloatChip className="-right-2 bottom-10 sm:-right-6" delay={0.7} reduce={reduce}>
            <div className="flex items-center gap-2">
              <span className="relative flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-pulse-dot rounded-full bg-brand-500" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-600" />
              </span>
              <span className="text-xs font-medium text-ink">Synced to FBR</span>
            </div>
          </FloatChip>
        </motion.div>
      </div>
    </section>
  );
}

function FloatChip({
  children,
  className,
  delay,
  reduce,
}: {
  children: React.ReactNode;
  className?: string;
  delay: number;
  reduce: boolean | null;
}) {
  return (
    <motion.div
      {...(reduce
        ? {}
        : {
            initial: { opacity: 0, y: 12 },
            animate: { opacity: 1, y: 0 },
            transition: { duration: 0.5, delay },
          })}
      className={cn(
        "absolute flex flex-col gap-0.5 rounded-xl border border-slate-100 bg-white/95 px-4 py-3 shadow-card backdrop-blur",
        className,
      )}
    >
      {children}
    </motion.div>
  );
}
