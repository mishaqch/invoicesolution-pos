# Invoice PDF assets

Drop binary assets here that the PDF renderer (`invoice_pdf.py`) loads.

## `fbr_di_logo.png`

The official FBR Digital Invoicing wordmark/logo. Place a PNG here at any
size — the renderer rescales it to ~22×18mm in the top-right of the
invoice header.

PRAL distributes the logo with their integrator onboarding; until you
have it on disk the PDF simply omits the FBR logo (the QR code still
renders when the invoice has an `fbr_qr_payload`).

If you have the PRAL-issued asset, copy it to this folder:

```sh
cp /path/to/fbr-di-logo.png backend/apps/sales/assets/fbr_di_logo.png
```

## Per-tenant logo

Tenants upload their business logo separately. The renderer looks for it
at `MEDIA_ROOT/tenants/<tenant-id>-logo.png`. If absent, the PDF
header just shows the tenant business name in text.
