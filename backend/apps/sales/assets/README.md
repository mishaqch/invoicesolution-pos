# Invoice PDF assets

Binary assets the PDF renderer (`invoice_pdf.py`) loads. Square images
work best — the renderer fits the FBR logo into a 30×30mm slot next to
the QR code.

## FBR Digital Invoicing logo

The renderer accepts either filename, in this order:

1. `fbrLogo.png` (preferred — what you save the PRAL-issued file as)
2. `fbr_di_logo.png` (legacy name, kept for backward compatibility)

A square PNG at 512×512 or 1024×1024 with transparent or white
background works well. Drop the file into this folder and re-render —
no code change needed:

```sh
cp /path/to/fbr-logo.png backend/apps/sales/assets/fbrLogo.png
```

If neither file is present, the renderer falls back to a vector-drawn
placeholder (green leaf "D" + "DIGITAL INVOICING" wordmark).

## Per-tenant logo

Each tenant uploads their business logo separately. The renderer
looks for it at `MEDIA_ROOT/tenants/<tenant-id>-logo.png`. When
absent, the PDF header just shows the tenant business name in text.
