#!/usr/bin/env bash
# Generate a BLACK, thermal-ready receipt logo from a color source image.
#
# Usage:  ./scripts/make-receipt-logo.sh <source-logo.png>
#
# Output: electron/assets/receipt-logo.png
#   - Recolored to solid BLACK on a WHITE background (thermal printers are 1-bit:
#     dark pixels burn as dots). Transparency is flattened to white so only the
#     logo shape prints.
#   - Resized to 384px wide (full 80mm thermal width; scale down for 58mm).
#
# Prefers ImageMagick (best quality). Falls back to `sips` (macOS built-in),
# which flattens + resizes but cannot recolor to a flat black — for `sips`,
# supply an already-monochrome source, or install ImageMagick:  brew install imagemagick
set -euo pipefail

SRC="${1:?Usage: make-receipt-logo.sh <source-logo.png>}"
OUT_DIR="$(cd "$(dirname "$0")/.." && pwd)/electron/assets"
OUT="$OUT_DIR/receipt-logo.png"
WIDTH=384

mkdir -p "$OUT_DIR"

if command -v magick >/dev/null 2>&1 || command -v convert >/dev/null 2>&1; then
  IM="$(command -v magick || command -v convert)"
  # Flatten transparency onto white, turn every non-white/opaque pixel black,
  # trim surrounding whitespace, pad a small margin, resize to thermal width.
  "$IM" "$SRC" \
    -background white -alpha remove -alpha off \
    -colorspace Gray -threshold 78% -negate \
    -trim +repage -bordercolor white -border 8 \
    -resize ${WIDTH}x \
    -colorspace Gray -type Grayscale \
    "$OUT"
  echo "Wrote $OUT (ImageMagick, ${WIDTH}px wide, black-on-white)"
elif command -v sips >/dev/null 2>&1; then
  # sips can flatten + resize but not recolor; assumes a usable source.
  TMP="$(mktemp -t receiptlogo).png"
  sips -s format png "$SRC" --out "$TMP" >/dev/null
  sips --resampleWidth "$WIDTH" "$TMP" --out "$OUT" >/dev/null
  rm -f "$TMP"
  echo "Wrote $OUT (sips, ${WIDTH}px wide). NOTE: install ImageMagick for a true black recolor."
else
  echo "Need ImageMagick (brew install imagemagick) or sips to build the logo." >&2
  exit 1
fi
