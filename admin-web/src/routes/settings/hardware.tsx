import {
  Check,
  CircuitBoard,
  Monitor,
  Printer,
  Scale,
  Wallet,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DeviceCheck {
  icon: React.ComponentType<{ className?: string }>;
  device: string;
  test: string;
  doc: string;
}

const DEVICES: DeviceCheck[] = [
  {
    icon: Wallet,
    device: "Cash drawer",
    test: "Open Settings → Hardware on the POS terminal app and tap Open drawer. The drawer should open with an audible thunk.",
    doc: "See INTEGRATIONS.md §3.4 for ESC/POS drawer kick code.",
  },
  {
    icon: Printer,
    device: "Thermal printer",
    test: "Tap Print test page on the POS Hardware screen. A receipt with sample lines, a tax breakdown, and a sample QR should print legibly.",
    doc: "Verify Urdu rendering uses the bitmap path (INTEGRATIONS.md §3.1). 58mm and 80mm both supported.",
  },
  {
    icon: Monitor,
    device: "Customer-facing display",
    test: "On the POS terminal Hardware screen, tap Show test slide. The customer monitor should switch from idle promo to a sample sale-in-progress view.",
    doc: "Customer display runs in the same Electron process on a second monitor.",
  },
  {
    icon: Scale,
    device: "Weighing scale",
    test: "Tap Read scale. The current weight should appear within 500ms. Place a known reference weight and verify the reading.",
    doc: "Serial integration is V1.5 — flag as deferred if your shop does not weigh items at checkout.",
  },
  {
    icon: CircuitBoard,
    device: "Barcode scanner",
    test: "Scan any product. The product should appear in the cart instantly. If the scanner sends an Enter keystroke after the code, behavior is correct.",
    doc: "Most USB scanners are HID and need no driver. Configure the scanner to send Enter as the suffix.",
  },
];

/**
 * Admin-side hardware checklist. Actual hardware tests run from the POS
 * terminal Electron app where the bridge to drawer / printer / scale lives.
 * This page documents what to test on each cashier station before going
 * live with a new shop or replacement device.
 */
export default function HardwareChecklist() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Hardware checklist</h1>
        <p className="text-sm text-muted-foreground">
          Run these checks on every cashier station before opening the shop.
        </p>
      </div>

      <ol className="space-y-3">
        {DEVICES.map((d, idx) => {
          const Icon = d.icon;
          return (
            <li key={d.device}>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Icon className="h-4 w-4" aria-hidden />
                    {idx + 1}. {d.device}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  <p>{d.test}</p>
                  <p className="text-xs text-muted-foreground">{d.doc}</p>
                  <label className="flex items-center gap-2 text-xs">
                    <input type="checkbox" className="h-3.5 w-3.5" />
                    <span className="text-muted-foreground">Verified working</span>
                  </label>
                </CardContent>
              </Card>
            </li>
          );
        })}
      </ol>

      <Card className="border-green-300 bg-green-50/50 dark:bg-green-950/20">
        <CardContent className="flex items-start gap-2 pt-4 text-sm">
          <Check className="mt-0.5 h-4 w-4 text-green-600" aria-hidden />
          <div>
            <p className="font-medium">All five checks passed?</p>
            <p className="text-xs text-muted-foreground">
              The terminal is ready for production use. Document the device serials in your asset register.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
