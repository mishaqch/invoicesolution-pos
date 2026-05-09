import { Check, Circle, X } from "lucide-react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import {
  shouldShowOnboarding,
  useOnboarding,
  useUpdateOnboarding,
  type OnboardingState,
} from "./queries";

interface Step {
  key: keyof OnboardingState["derived"];
  title: string;
  description: string;
  cta: string;
  href: string;
}

const STEPS: Step[] = [
  {
    key: "has_branch",
    title: "Add your first branch",
    description: "Branches are physical store locations. Most owners start with one.",
    cta: "Open branches",
    href: "/branches",
  },
  {
    key: "has_terminal",
    title: "Register a POS terminal",
    description: "A terminal is one cash counter. You can add more later.",
    cta: "Open branches",
    href: "/branches",
  },
  {
    key: "has_product",
    title: "Add at least one product",
    description: "You can also import a CSV of your full catalog.",
    cta: "Open products",
    href: "/catalog/products",
  },
  {
    key: "has_first_sale",
    title: "Make your first sale",
    description: "Open the POS terminal app on a real cashier station and ring up a sale.",
    cta: "POS user guide",
    href: "/help/first-sale",
  },
];

/**
 * Inline-card wizard rendered above the dashboard until either every
 * derived flag is true OR the user dismisses it. Each step links to the
 * relevant existing route — no new "wizard" routes, the wizard is a UX
 * overlay on top of the surfaces that already exist.
 */
export function OnboardingWizard() {
  const { data } = useOnboarding();
  const update = useUpdateOnboarding();

  if (!shouldShowOnboarding(data)) return null;
  const derived = data!.derived;
  const completed = STEPS.filter((s) => derived[s.key]).length;

  return (
    <Card className="border-primary/30 bg-primary/5">
      <CardHeader className="flex flex-row items-start justify-between pb-2">
        <div>
          <CardTitle className="text-base">Welcome to your new POS</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {completed} of {STEPS.length} done · target: a sale within 30 minutes
          </p>
        </div>
        <button
          type="button"
          aria-label="Dismiss"
          onClick={() => update.mutate({ dismissed_at: new Date().toISOString() })}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent className="space-y-2">
        <ol className="space-y-2">
          {STEPS.map((step) => {
            const done = derived[step.key];
            return (
              <li
                key={step.key}
                className="flex items-start justify-between gap-3 rounded-md border bg-background p-3"
              >
                <div className="flex items-start gap-3">
                  {done ? (
                    <Check className="mt-0.5 h-4 w-4 text-green-600" aria-hidden />
                  ) : (
                    <Circle className="mt-0.5 h-4 w-4 text-muted-foreground" aria-hidden />
                  )}
                  <div>
                    <div className={done ? "text-sm line-through opacity-70" : "text-sm font-medium"}>
                      {step.title}
                    </div>
                    <div className="text-xs text-muted-foreground">{step.description}</div>
                  </div>
                </div>
                {!done && (
                  <Button asChild variant="outline" size="sm">
                    <Link to={step.href}>{step.cta}</Link>
                  </Button>
                )}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
