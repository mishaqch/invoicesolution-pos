/**
 * Windows raw ESC/POS printing — send bytes straight to an installed printer's
 * spooler as a RAW job, with NO native node module.
 *
 * Why this exists: node-thermal-printer's Windows story needs the native
 * `printer` module (a compiled dependency we don't bundle). Its only other
 * option treats the interface string as a file path, which does not work for a
 * USB thermal printer (e.g. the SPEED SP-200, 80mm, USB) — Windows exposes it
 * as an installed printer, not a device file. So a raw file write to
 * `//USB/NAME` or `/dev/usb/lp0` simply fails.
 *
 * The reliable path on Windows is the Win32 spooler API (winspool.drv:
 * OpenPrinter → StartDocPrinter(RAW) → WritePrinter → …). We drive it via a
 * short PowerShell P/Invoke script — present on every Windows box, no install.
 * This is the exact Windows analogue of the macOS/Linux `lp -o raw` path.
 *
 * Interface form: `win:<PrinterName>` (e.g. `win:POS-80` or `win:SP-200`).
 * Use `win:auto` to target the system default printer.
 */

import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

export interface WinPrintResult {
  success: boolean;
  reason?: string;
}

/** Is this a Windows raw-printer interface string? */
export function isWindowsInterface(uri: string): boolean {
  return /^win:/i.test(uri);
}

/** Extract the printer name from a `win:NAME` string ("" / "auto" ⇒ default). */
export function windowsPrinterName(uri: string): string {
  const raw = uri.replace(/^win:/i, "").trim();
  return raw && raw.toLowerCase() !== "auto" ? raw : "";
}

/**
 * List installed Windows printers (name + default flag) so the Hardware screen
 * can offer a picker. Returns [] on any failure (non-Windows, spawn error).
 */
export function listWindowsPrinters(): Promise<{ name: string; isDefault: boolean }[]> {
  if (process.platform !== "win32") return Promise.resolve([]);
  const ps = [
    "$ErrorActionPreference='Stop';",
    "$d=(Get-CimInstance Win32_Printer | Where-Object {$_.Default -eq $true} | Select-Object -First 1 -ExpandProperty Name);",
    "Get-CimInstance Win32_Printer | ForEach-Object { \"$($_.Name)`t$([int]($_.Name -eq $d))\" }",
  ].join(" ");
  return new Promise((resolve) => {
    let out = "";
    let done = false;
    const finish = (v: { name: string; isDefault: boolean }[]) => {
      if (!done) { done = true; resolve(v); }
    };
    let child;
    try {
      child = spawn("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command", ps], {
        stdio: ["ignore", "pipe", "ignore"],
        windowsHide: true,
      });
    } catch {
      return finish([]);
    }
    child.stdout?.on("data", (d: Buffer) => { out += d.toString(); });
    child.on("error", () => finish([]));
    child.on("close", () => {
      const rows = out
        .split(/\r?\n/)
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => {
          const [name, def] = l.split("\t");
          return { name: (name ?? "").trim(), isDefault: def?.trim() === "1" };
        })
        .filter((r) => r.name);
      finish(rows);
    });
    // Safety timeout.
    setTimeout(() => finish([]), 8000);
  });
}

/**
 * Spool raw bytes to a Windows printer via winspool.drv WritePrinter (RAW).
 * `printerName` empty ⇒ the system default printer.
 */
export function printRawWindows(
  buffer: Buffer,
  printerName: string,
  timeoutMs = 15000,
): Promise<WinPrintResult> {
  if (process.platform !== "win32") {
    return Promise.resolve({ success: false, reason: "win: interface is only valid on Windows" });
  }

  // Write the ESC/POS bytes to a temp file; PowerShell reads it back as bytes
  // and hands them to WritePrinter. (Passing raw binary on the command line is
  // not safe; a temp file is.) The script itself is written to a .ps1 and run
  // via -File, which is far more reliable than piping to `-Command -` (stdin
  // buffering there was swallowing our success marker → false "exit 0" errors).
  let dir = "";
  let dataPath = "";
  let scriptPath = "";
  try {
    dir = mkdtempSync(path.join(tmpdir(), "posprint-"));
    dataPath = path.join(dir, "job.bin");
    scriptPath = path.join(dir, "print.ps1");
    writeFileSync(dataPath, buffer);
  } catch (e) {
    return Promise.resolve({ success: false, reason: `temp write failed: ${e instanceof Error ? e.message : String(e)}` });
  }

  // PowerShell P/Invoke into winspool.drv. If no name is given, resolve the
  // default printer first. Prints as a RAW job (ESC/POS passes through
  // untouched — the driver does NOT rasterize it). We embed the printer name
  // and data path as literal here-strings so odd characters/spaces are safe,
  // and print an explicit PRINT_OK / PRINT_ERR: marker so the caller can tell
  // real success from a driver/spooler failure regardless of exit code.
  const script = `
$ErrorActionPreference = 'Stop'
try {
  $printer = @'
${printerName}
'@.Trim()
  if (-not $printer) {
    $printer = (Get-CimInstance Win32_Printer | Where-Object { $_.Default -eq $true } | Select-Object -First 1 -ExpandProperty Name)
  }
  if (-not $printer) { Write-Output 'PRINT_ERR: no printer name and no default printer'; exit 3 }

  $sig = @'
using System;
using System.IO;
using System.Runtime.InteropServices;
public class RawPrinterHelper {
  [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
  public struct DOCINFOW { [MarshalAs(UnmanagedType.LPWStr)] public string pDocName; [MarshalAs(UnmanagedType.LPWStr)] public string pOutputFile; [MarshalAs(UnmanagedType.LPWStr)] public string pDataType; }
  [DllImport("winspool.drv", CharSet=CharSet.Unicode, SetLastError=true)] public static extern bool OpenPrinter(string src, out IntPtr hPrinter, IntPtr pd);
  [DllImport("winspool.drv", SetLastError=true)] public static extern bool ClosePrinter(IntPtr hPrinter);
  [DllImport("winspool.drv", CharSet=CharSet.Unicode, SetLastError=true)] public static extern int StartDocPrinter(IntPtr hPrinter, int level, ref DOCINFOW di);
  [DllImport("winspool.drv", SetLastError=true)] public static extern bool EndDocPrinter(IntPtr hPrinter);
  [DllImport("winspool.drv", SetLastError=true)] public static extern bool StartPagePrinter(IntPtr hPrinter);
  [DllImport("winspool.drv", SetLastError=true)] public static extern bool EndPagePrinter(IntPtr hPrinter);
  [DllImport("winspool.drv", SetLastError=true)] public static extern bool WritePrinter(IntPtr hPrinter, IntPtr pBytes, int dwCount, out int dwWritten);
  // Try one specific spooler data type. Returns the Win32 error from
  // StartDocPrinter (0 = success). Different drivers accept different types:
  //   RAW  → real ESC/POS thermal drivers (POS-80, manufacturer driver)
  //   TEXT → the "Generic / Text Only" driver (rejects RAW with Win32 1905)
  static int TrySend(string printer, byte[] bytes, string dataType) {
    IntPtr h; DOCINFOW di = new DOCINFOW(); di.pDocName = "POS Receipt"; di.pDataType = dataType;
    if (!OpenPrinter(printer, out h, IntPtr.Zero)) throw new Exception("OpenPrinter failed (Win32 " + Marshal.GetLastWin32Error() + "). Check the printer name.");
    try {
      if (StartDocPrinter(h, 1, ref di) == 0) { return Marshal.GetLastWin32Error(); }
      try {
        if (!StartPagePrinter(h)) throw new Exception("StartPagePrinter failed (Win32 " + Marshal.GetLastWin32Error() + ")");
        IntPtr p = Marshal.AllocHGlobal(bytes.Length);
        try { Marshal.Copy(bytes, 0, p, bytes.Length); int written;
          if (!WritePrinter(h, p, bytes.Length, out written)) throw new Exception("WritePrinter failed (Win32 " + Marshal.GetLastWin32Error() + ")"); }
        finally { Marshal.FreeHGlobal(p); }
        EndPagePrinter(h);
      } finally { EndDocPrinter(h); }
      return 0;
    } finally { ClosePrinter(h); }
  }
  public static void Send(string printer, string file) {
    byte[] bytes = File.ReadAllBytes(file);
    // Prefer RAW (ESC/POS passes through untouched). If the installed driver
    // rejects RAW (Generic/Text Only → Win32 1905), fall back to TEXT so the
    // receipt still prints on whatever driver the operator has installed.
    int err = TrySend(printer, bytes, "RAW");
    if (err == 0) return;
    if (err == 1905 || err == 2 || err == 3) {
      // The driver rejected RAW (typically Generic/Text Only). Retry as TEXT,
      // but first strip ESC/POS control bytes so the receipt reads cleanly
      // instead of printing control-code garbage. Keep printable ASCII, tab,
      // newline and carriage-return; drop the rest (init, cut, charset, QR…).
      byte[] plain = StripControl(bytes);
      int err2 = TrySend(printer, plain, "TEXT");
      if (err2 == 0) return;
      throw new Exception("StartDocPrinter failed for RAW (Win32 " + err + ") and TEXT (Win32 " + err2 + "). The printer driver may not support raw printing.");
    }
    throw new Exception("StartDocPrinter failed (Win32 " + err + ")");
  }
  static byte[] StripControl(byte[] input) {
    System.Collections.Generic.List<byte> outb = new System.Collections.Generic.List<byte>(input.Length);
    for (int i = 0; i < input.Length; i++) {
      byte b = input[i];
      // ESC (0x1B) and GS (0x1D) start multi-byte ESC/POS commands; skip the
      // command intro bytes so their parameters don't print as noise. We keep
      // it simple: drop ESC/GS and the immediate following byte, keep the rest.
      if (b == 0x1B || b == 0x1D) { i++; continue; }
      if (b == 0x0A || b == 0x0D || b == 0x09) { outb.Add(b); continue; } // LF/CR/TAB
      if (b >= 0x20 && b <= 0x7E) { outb.Add(b); continue; }             // printable ASCII
      // else: drop (non-printable / high-bit charset bytes)
    }
    // Ensure the paper advances a few lines at the end (no cut on text driver).
    outb.Add(0x0A); outb.Add(0x0A); outb.Add(0x0A); outb.Add(0x0A);
    return outb.ToArray();
  }
}
'@
  Add-Type -TypeDefinition $sig -Language CSharp
  [RawPrinterHelper]::Send($printer, @'
${dataPath}
'@.Trim())
  Write-Output 'PRINT_OK'
} catch {
  Write-Output ('PRINT_ERR: ' + $_.Exception.Message)
  exit 1
}
`;

  try {
    writeFileSync(scriptPath, "﻿" + script, { encoding: "utf8" });
  } catch (e) {
    return Promise.resolve({ success: false, reason: `temp script write failed: ${e instanceof Error ? e.message : String(e)}` });
  }

  return new Promise((resolve) => {
    let done = false;
    let stderr = "";
    let stdout = "";
    const cleanup = () => { try { if (dir) rmSync(dir, { recursive: true, force: true }); } catch { /* ignore */ } };
    const finish = (r: WinPrintResult) => {
      if (done) return;
      done = true;
      cleanup();
      resolve(r);
    };

    let child;
    try {
      child = spawn(
        "powershell.exe",
        ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath],
        { stdio: ["ignore", "pipe", "pipe"], windowsHide: true },
      );
    } catch (e) {
      return finish({ success: false, reason: `powershell spawn failed: ${e instanceof Error ? e.message : String(e)}` });
    }

    const timer = setTimeout(() => {
      try { child?.kill(); } catch { /* ignore */ }
      finish({ success: false, reason: `windows print timeout (${timeoutMs / 1000}s)` });
    }, timeoutMs);

    child.stdout?.on("data", (d: Buffer) => { stdout += d.toString(); });
    child.stderr?.on("data", (d: Buffer) => { stderr += d.toString(); });
    child.on("error", (e: Error) => {
      clearTimeout(timer);
      finish({ success: false, reason: `powershell error: ${e.message}` });
    });
    child.on("close", (code: number) => {
      clearTimeout(timer);
      const out = (stdout + "\n" + stderr).trim();
      // Success is signalled by our explicit marker — the most reliable signal.
      // Fall back to exit code 0 (some environments strip stdout) but only when
      // there is no explicit error marker.
      if (/PRINT_OK/.test(out)) {
        finish({ success: true });
      } else if (/PRINT_ERR:/.test(out)) {
        const m = out.match(/PRINT_ERR:[^\r\n]*/);
        finish({ success: false, reason: `windows print failed: ${(m?.[0] ?? "unknown").replace("PRINT_ERR:", "").trim()}` });
      } else if (code === 0) {
        // Ran cleanly but produced no marker — treat as success (job spooled).
        finish({ success: true });
      } else {
        const msg = out ? out.split(/\r?\n/).slice(0, 4).join(" ") : `exit ${code}`;
        finish({ success: false, reason: `windows print failed: ${msg}` });
      }
    });
  });
}
