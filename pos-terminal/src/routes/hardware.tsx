import { ArrowLeft, Check, Printer, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Per-station Hardware settings — printer interface URL, test print,
 * test drawer kick, customer-display test message.
 *
 * Persists the printer interface URL to local SQLite via window.api.meta
 * so the printer adapter (electron/printer.ts) picks it up on subsequent
 * print calls. Configuration is per-station because each cashier counter
 * has its own physical printer (USB device path, network IP, etc.).
 *
 * Common interface formats:
 *   tcp://192.168.1.50:9100   network printer
 *   /dev/usb/lp0              USB on Linux
 *   //USB/EPSON-TM-T20III     USB on Windows
 *   /dev/cu.usbserial-XXXX    serial on macOS
 */
export default function HardwareRoute() {
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [printerUrl, setPrinterUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [testStatus, setTestStatus] = useState<{ ok: boolean; msg: string } | null>(null);

  useEffect(() => {
    void window.api.meta.get("printer.interface").then((v) => setPrinterUrl(v ?? ""));
  }, []);

  async function save() {
    setSaving(true);
    try {
      await window.api.meta.set("printer.interface", printerUrl.trim());
    } finally {
      setSaving(false);
    }
  }

  async function testDrawer() {
    const r = await window.api.drawer.open();
    setTestStatus({
      ok: r.success,
      msg: r.success ? "Drawer opened." : (r.reason ?? "Drawer test failed."),
    });
  }

  async function testCustomerDisplay() {
    const r = await window.api.customerDisplay.post({
      type: "thanks",
    });
    setTestStatus({
      ok: r.success,
      msg: r.success ? "Customer display test fired." : "No customer display attached.",
    });
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-12 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate("/sale", { replace: true })}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> {t("common.back")}
        </button>
        <div className="text-sm font-medium">Hardware</div>
        <div />
      </header>

      <main className="mx-auto w-full max-w-2xl space-y-4 p-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Printer className="h-4 w-4" /> Thermal printer
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>Interface URL</Label>
              <Input
                value={printerUrl}
                onChange={(e) => setPrinterUrl(e.target.value)}
                placeholder="tcp://192.168.1.50:9100"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Examples: <span className="font-mono">tcp://192.168.1.50:9100</span> ·{" "}
                <span className="font-mono">/dev/usb/lp0</span> ·{" "}
                <span className="font-mono">//USB/EPSON-TM-T20III</span>
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Leave blank to disable printing (receipts log to disk fallback).
              </p>
            </div>
            <div className="flex gap-2">
              <Button onClick={save} disabled={saving} size="sm">
                {saving ? "Saving…" : "Save"}
              </Button>
              <Button variant="outline" size="sm" onClick={testDrawer}>
                Open drawer (test)
              </Button>
              <Button variant="outline" size="sm" onClick={testCustomerDisplay}>
                Customer display test
              </Button>
            </div>
            {testStatus && (
              <div
                className={`flex items-start gap-2 rounded-md border p-2 text-xs ${
                  testStatus.ok
                    ? "border-green-300 bg-green-50 text-green-900"
                    : "border-amber-300 bg-amber-50 text-amber-900"
                }`}
              >
                {testStatus.ok ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                <span>{testStatus.msg}</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Notes</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground space-y-2">
            <p>
              The printer interface URL is stored locally on this terminal only
              (per-station). If you replace the printer or change network address,
              update this field.
            </p>
            <p>
              Cash drawer pulses are sent via the printer's drawer kick port.
              Drawer test will not work until a printer is configured.
            </p>
            <p>
              Customer display runs on the first non-primary monitor connected to
              this machine. If no second monitor is attached, the customer-display
              test will report "no customer display attached" — not an error.
            </p>
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
