import { ArrowLeft, Check, Printer, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import type { PosPairedIdentity } from "../../electron/preload";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSessionStore } from "@/stores/session";

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
  const [testing, setTesting] = useState(false);
  // Kitchen printer (restaurant): a SEPARATE network printer in the kitchen that
  // auto-prints KOTs. Blank = KOTs fall back to the counter printer above.
  const [kitchenUrl, setKitchenUrl] = useState("");
  const [kitchenTesting, setKitchenTesting] = useState(false);
  const [kitchenTestStatus, setKitchenTestStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  // Installed Windows printers (USB thermal printers show up here). Empty on
  // macOS/Linux — those use tcp:// or cups:// interfaces instead.
  const [winPrinters, setWinPrinters] = useState<{ name: string; isDefault: boolean }[]>([]);

  // Non-fiscal tenants (fbr_connection_type="none", e.g. TDCP — no FBR link)
  // must not see the FBR Fiscalization (SDC) settings at all. Fiscal tenants
  // still get the full section.
  const isFiscal = useSessionStore((st) => st.tenant?.fbr_connection_type) !== "none";

  // FBR SDC (Fiscalization service) — base URL + paired identity.
  const [sdcUrl, setSdcUrl] = useState("");
  const [sdcSaving, setSdcSaving] = useState(false);
  const [sdcStatus, setSdcStatus] = useState<{ ok: boolean; msg: string } | null>(null);
  const [identity, setIdentity] = useState<PosPairedIdentity | null>(null);

  useEffect(() => {
    void window.api.meta.get("printer.interface").then((v) => setPrinterUrl(v ?? ""));
    void window.api.meta.get("kitchen.interface").then((v) => setKitchenUrl(v ?? ""));
    void window.api.sdc.getUrl().then((v) => setSdcUrl(v ?? ""));
    void window.api.pairing.status().then((s) => setIdentity(s.identity));
    // Load installed Windows printers so the operator can pick instead of
    // hand-typing the interface. No-op (empty) on macOS/Linux.
    void window.api.printer.listWindows?.().then((list) => setWinPrinters(list ?? [])).catch(() => {});
  }, []);

  async function testPrint() {
    setTesting(true);
    setTestStatus(null);
    try {
      const r = await window.api.printer.test?.(printerUrl.trim() || undefined);
      setTestStatus({
        ok: !!r?.success,
        msg: r?.success
          ? "Test slip sent to the printer."
          : (r?.reason ?? "Test print failed.") +
            (r?.fallbackPath ? ` (saved to ${r.fallbackPath})` : ""),
      });
    } finally {
      setTesting(false);
    }
  }

  async function saveSdc() {
    setSdcSaving(true);
    try {
      await window.api.sdc.setUrl(sdcUrl.trim());
    } finally {
      setSdcSaving(false);
    }
  }

  async function testSdc() {
    const r = await window.api.sdc.health();
    setSdcStatus({ ok: r.ok, msg: r.message });
  }

  async function unpairTerminal() {
    if (!window.confirm(
      "Unpair this terminal? It will need a new pairing code to ring sales again.",
    )) return;
    await window.api.pairing.unpair();
    navigate("/", { replace: true });
  }

  async function save() {
    setSaving(true);
    try {
      await window.api.meta.set("printer.interface", printerUrl.trim());
      // Persist the kitchen printer too (blank clears it → KOTs use the counter
      // printer). Both saved together from the one Save button.
      await window.api.meta.set("kitchen.interface", kitchenUrl.trim());
    } finally {
      setSaving(false);
    }
  }

  // Test the kitchen printer specifically — prints a test slip to the kitchen
  // printer address so you can verify ON-SITE that the terminal reaches it over
  // the network (same router/bridged extender). Saves the typed value first so
  // the test uses exactly what will be saved.
  async function testKitchenPrint() {
    const target = kitchenUrl.trim();
    // A kitchen test needs a kitchen printer address. Without one the underlying
    // test would fall back to the COUNTER printer (or disk) and wrongly look
    // like the kitchen printer works — so require an address here.
    if (!target) {
      setKitchenTestStatus({
        ok: false,
        msg: "Enter the kitchen printer address first (e.g. tcp://192.168.0.60:9100), then test.",
      });
      return;
    }
    setKitchenTesting(true);
    setKitchenTestStatus(null);
    try {
      await window.api.meta.set("kitchen.interface", target);
      // Pass the explicit kitchen address so the test targets IT, not the
      // counter printer.
      const r = await window.api.printer.test?.(target);
      setKitchenTestStatus({
        ok: !!r?.success,
        msg: r?.success
          ? `Test slip sent to the kitchen printer (${target}).`
          : (r?.reason ?? "Kitchen printer unreachable — check the address and network.") +
            (r?.fallbackPath ? ` (saved to ${r.fallbackPath})` : ""),
      });
    } finally {
      setKitchenTesting(false);
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
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex h-12 shrink-0 items-center justify-between border-b px-4">
        <button
          onClick={() => navigate("/sale", { replace: true })}
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> {t("common.back")}
        </button>
        <div className="text-sm font-medium">Hardware</div>
        <div />
      </header>

      <main className="mx-auto min-h-0 w-full max-w-2xl flex-1 space-y-4 overflow-y-auto p-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Printer className="h-4 w-4" /> Thermal printer
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* USB printer on Windows: the operator types the EXACT Windows
                printer name (Control Panel → Printers, or `wmic printer get
                name`). Stored as win:<name>. A free-text field means any
                printer works with no rebuild — the installed list below is
                only an optional shortcut, never a hard dependency. */}
            <div>
              <Label>Printer name (USB / Windows)</Label>
              <Input
                value={printerUrl.startsWith("win:") ? printerUrl.slice(4) : ""}
                onChange={(e) => setPrinterUrl(e.target.value ? `win:${e.target.value}` : "")}
                placeholder="e.g. Thermal Small Printer"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                Type the exact Windows printer name — see it in{" "}
                <span className="font-mono">Printers &amp; scanners</span>, or run{" "}
                <span className="font-mono">wmic printer get name</span>. Then click Test print.
              </p>
              {winPrinters.length > 0 && (
                <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
                  <span>Detected:</span>
                  {winPrinters.map((p) => (
                    <button
                      key={p.name}
                      type="button"
                      onClick={() => setPrinterUrl(`win:${p.name}`)}
                      className="rounded border px-1.5 py-0.5 font-mono hover:bg-muted"
                      title="Use this printer name"
                    >
                      {p.name}{p.isDefault ? " ★" : ""}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none">Advanced: full interface URL</summary>
              <div className="mt-2 space-y-1">
                <Input
                  value={printerUrl}
                  onChange={(e) => setPrinterUrl(e.target.value)}
                  placeholder="win:Thermal Small Printer"
                />
                <p>
                  USB on Windows: <span className="font-mono">win:PrinterName</span> (or{" "}
                  <span className="font-mono">win:auto</span> for the default).{" "}
                  Network: <span className="font-mono">tcp://192.168.1.50:9100</span>.{" "}
                  Leave blank to disable printing.
                </p>
              </div>
            </details>
            <div className="flex flex-wrap gap-2">
              <Button onClick={save} disabled={saving} size="sm">
                {saving ? "Saving…" : "Save"}
              </Button>
              <Button variant="outline" size="sm" onClick={testPrint} disabled={testing}>
                {testing ? "Printing…" : "Test print"}
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
                    ? "bg-success-soft text-success-soft-foreground"
                    : "bg-warning-soft text-warning-soft-foreground"
                }`}
              >
                {testStatus.ok ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                <span>{testStatus.msg}</span>
              </div>
            )}

            {/* Kitchen printer (restaurant) — a SEPARATE printer in the kitchen
                that auto-prints KOTs when the cashier sends an order to the
                kitchen. No PC/screen needed in the kitchen, just the printer.
                Leave blank to print KOTs on the counter printer above. */}
            <div className="mt-4 border-t pt-3">
              <div className="text-sm font-medium">Kitchen printer (optional)</div>
              <p className="mt-1 text-xs text-muted-foreground">
                Separate printer in the kitchen for order tickets (KOTs). Enter its
                network address, e.g. <span className="font-mono">tcp://192.168.0.60:9100</span>.
                It must be on the same network as this terminal. Leave blank to print
                KOTs on the counter printer.
              </p>
              <div className="mt-2 space-y-1">
                <Input
                  value={kitchenUrl}
                  onChange={(e) => setKitchenUrl(e.target.value)}
                  placeholder="tcp://192.168.0.60:9100"
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={testKitchenPrint}
                  disabled={kitchenTesting}
                >
                  {kitchenTesting ? "Printing…" : "Test kitchen printer"}
                </Button>
              </div>
              {kitchenTestStatus && (
                <div
                  className={`mt-2 flex items-start gap-2 rounded-md border p-2 text-xs ${
                    kitchenTestStatus.ok
                      ? "bg-success-soft text-success-soft-foreground"
                      : "bg-warning-soft text-warning-soft-foreground"
                  }`}
                >
                  {kitchenTestStatus.ok ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                  <span>{kitchenTestStatus.msg}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {isFiscal ? (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
                <ShieldCheck className="h-4 w-4" /> FBR Fiscalization (SDC)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {identity && (
                <div className="rounded-md border bg-muted/40 p-3 text-xs">
                  <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                    <span className="text-muted-foreground">Branch</span>
                    <span className="font-medium">{identity.branchName} ({identity.branchCode})</span>
                    <span className="text-muted-foreground">Terminal</span>
                    <span className="font-medium">{identity.terminalName} · T{identity.terminalIndex}</span>
                    <span className="text-muted-foreground">FBR POS ID</span>
                    <span className="font-mono">{identity.branchFbrPosId ?? "—"}</span>
                  </div>
                </div>
              )}
              <div>
                <Label>SDC service URL</Label>
                <Input
                  value={sdcUrl}
                  onChange={(e) => setSdcUrl(e.target.value)}
                  placeholder="http://localhost:8524"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  The FBR Fiscalization service runs on this machine — leave as{" "}
                  <span className="font-mono">http://localhost:8524</span>. If the
                  branch shares one fiscal machine, point this at that machine,
                  e.g. <span className="font-mono">http://192.168.1.10:8524</span>.
                </p>
              </div>
              <div className="flex gap-2">
                <Button onClick={saveSdc} disabled={sdcSaving} size="sm">
                  {sdcSaving ? "Saving…" : "Save"}
                </Button>
                <Button variant="outline" size="sm" onClick={testSdc}>
                  Test SDC connection
                </Button>
                {identity && (
                  <Button variant="outline" size="sm" onClick={unpairTerminal}>
                    Unpair terminal
                  </Button>
                )}
              </div>
              {sdcStatus && (
                <div
                  className={`flex items-start gap-2 rounded-md border p-2 text-xs ${
                    sdcStatus.ok
                      ? "bg-success-soft text-success-soft-foreground"
                      : "bg-warning-soft text-warning-soft-foreground"
                  }`}
                >
                  {sdcStatus.ok ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                  <span className="break-all">{sdcStatus.msg}</span>
                </div>
              )}
            </CardContent>
          </Card>
        ) : (
          // Non-fiscal tenant (TDCP): NO FBR section. Keep a minimal Terminal card
          // so branch/terminal identity + Unpair are still reachable.
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Terminal</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {identity && (
                <div className="rounded-md border bg-muted/40 p-3 text-xs">
                  <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                    <span className="text-muted-foreground">Branch</span>
                    <span className="font-medium">{identity.branchName} ({identity.branchCode})</span>
                    <span className="text-muted-foreground">Terminal</span>
                    <span className="font-medium">{identity.terminalName} · T{identity.terminalIndex}</span>
                  </div>
                </div>
              )}
              {identity && (
                <Button variant="outline" size="sm" onClick={unpairTerminal}>
                  Unpair terminal
                </Button>
              )}
            </CardContent>
          </Card>
        )}

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
