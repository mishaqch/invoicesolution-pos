/**
 * Build the FBR compliance "stamp" — the FBR Digital Invoicing logo on the LEFT
 * and the invoice QR on the RIGHT, side-by-side, as ONE composite PNG.
 *
 * Why composite into a single image: thermal printers (ESC/POS) render
 * top-to-bottom line by line, so you can't natively place a raster logo and a
 * QR on the same horizontal band. Compositing both into one bitmap and printing
 * it with `printImageBuffer` is the reliable way to get a true side-by-side
 * layout. The QR encodes the bare FBR invoice number (what Tax Asaan verifies).
 */

import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { PNG } from "pngjs";
import QRCode from "qrcode";

function resolveFbrLogoPath(): string | null {
  const rel = "fbr-logo-thermal.png";
  const candidates = [
    path.resolve(process.cwd(), "electron/assets", rel),
    path.resolve(__dirname, "assets", rel),
    path.resolve(__dirname, "../../electron/assets", rel),
    path.resolve(__dirname, "../electron/assets", rel),
  ];
  return candidates.find((p) => existsSync(p)) ?? null;
}

/** Nearest-neighbour resize of a pngjs image to w×h (keeps it crisp for QR). */
function resize(src: PNG, w: number, h: number): PNG {
  const dst = new PNG({ width: w, height: h });
  for (let y = 0; y < h; y++) {
    const sy = Math.floor((y * src.height) / h);
    for (let x = 0; x < w; x++) {
      const sx = Math.floor((x * src.width) / w);
      const si = (src.width * sy + sx) << 2;
      const di = (w * y + x) << 2;
      dst.data[di] = src.data[si];
      dst.data[di + 1] = src.data[si + 1];
      dst.data[di + 2] = src.data[si + 2];
      dst.data[di + 3] = src.data[si + 3];
    }
  }
  return dst;
}

/** Blit `img` onto `canvas` at (ox, oy), compositing over white. */
function blit(canvas: PNG, img: PNG, ox: number, oy: number): void {
  for (let y = 0; y < img.height; y++) {
    const cy = oy + y;
    if (cy < 0 || cy >= canvas.height) continue;
    for (let x = 0; x < img.width; x++) {
      const cx = ox + x;
      if (cx < 0 || cx >= canvas.width) continue;
      const si = (img.width * y + x) << 2;
      const a = img.data[si + 3] / 255;
      const di = (canvas.width * cy + cx) << 2;
      for (let k = 0; k < 3; k++) {
        canvas.data[di + k] = Math.round(
          img.data[si + k] * a + canvas.data[di + k] * (1 - a),
        );
      }
      canvas.data[di + 3] = 255;
    }
  }
}

/**
 * Returns a PNG buffer: [ FBR logo | QR ] laid out side-by-side, sized to the
 * printer's dot width (default 576 for 80mm @ 203dpi; 384 for 58mm). Returns
 * null if the QR can't be built (caller falls back to a stacked QR-only print).
 */
export async function buildFbrStampPng(
  fbrNumber: string,
  dotWidth = 576,
): Promise<Buffer | null> {
  try {
    // QR as a pngjs image.
    const qrBuf = await QRCode.toBuffer(fbrNumber, {
      type: "png", errorCorrectionLevel: "M", margin: 1, scale: 6,
    });
    const qr = PNG.sync.read(qrBuf);

    // Target heights: a compact band. QR square sized to ~38% of width.
    const gap = Math.round(dotWidth * 0.04);
    const qrSize = Math.min(qr.width, Math.round(dotWidth * 0.40));
    const qrImg = resize(qr, qrSize, qrSize);

    // Logo: fit into the remaining left area, same height as the QR.
    let logoImg: PNG | null = null;
    const logoPath = resolveFbrLogoPath();
    if (logoPath) {
      const logo = PNG.sync.read(readFileSync(logoPath));
      const logoH = qrSize;
      const logoW = Math.min(
        Math.round((logo.width / logo.height) * logoH),
        dotWidth - qrSize - gap,
      );
      logoImg = resize(logo, Math.max(1, logoW), logoH);
    }

    const height = qrSize;
    const canvas = new PNG({ width: dotWidth, height });
    canvas.data.fill(255); // white background

    // Logo LEFT, QR RIGHT.
    if (logoImg) blit(canvas, logoImg, 0, 0);
    blit(canvas, qrImg, dotWidth - qrSize, 0);

    return PNG.sync.write(canvas);
  } catch (e) {
    console.warn("[fbr-stamp] composite failed:", e);
    return null;
  }
}
