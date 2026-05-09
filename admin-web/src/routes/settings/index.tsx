import {
  Activity,
  Building2,
  ChevronRight,
  CreditCard,
  FileText,
  HelpCircle,
  Receipt,
  Wrench,
} from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface SettingTile {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  description: string;
  to: string;
}

const TILES: SettingTile[] = [
  {
    icon: Building2,
    label: "Branches & terminals",
    description: "Manage shop locations and the POS terminals at each one.",
    to: "/branches",
  },
  {
    icon: CreditCard,
    label: "Payment methods",
    description: "Enable / disable cash, card, wallet, cheque, credit, store credit.",
    to: "/payments/settings",
  },
  {
    icon: Receipt,
    label: "Cheques",
    description: "Track issued and received cheques through clearance.",
    to: "/payments/cheques",
  },
  {
    icon: FileText,
    label: "FBR / PRAL",
    description: "Tokens, scenario tests, cancel-budget, manual amendments.",
    to: "/fbr",
  },
  {
    icon: Activity,
    label: "Sync health",
    description: "Per-terminal sync status and queued event counts.",
    to: "/sync",
  },
  {
    icon: Wrench,
    label: "Hardware",
    description: "Per-station bring-up checklist for drawer, printer, scale, scanner.",
    to: "/settings/hardware",
  },
  {
    icon: HelpCircle,
    label: "Help center",
    description: "FAQ and how-to articles for common workflows.",
    to: "/help",
  },
];

export default function SettingsIndex() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure your business, integrations, and devices.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {TILES.map((t) => {
          const Icon = t.icon;
          return (
            <Link key={t.to} to={t.to} className="group block">
              <Card className="h-full transition-colors hover:bg-accent">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2">
                      <Icon className="h-4 w-4" aria-hidden /> {t.label}
                    </span>
                    <ChevronRight className="h-4 w-4 opacity-50 transition-transform group-hover:translate-x-0.5" />
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-xs text-muted-foreground">
                  {t.description}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
