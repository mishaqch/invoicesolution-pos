interface Props {
  url: string;
  amount: string;
}

/**
 * Payment QR view — used by JazzCash / EasyPaisa / RaastID flows where the
 * customer scans a QR with their wallet app to pay. The URL embeds the
 * payment intent ID; the POS waits for the webhook before flipping to
 * the thank-you screen.
 */
export default function PaymentQR({ url, amount }: Props) {
  // We render the QR as an external image to avoid bundling a QR library
  // — in production swap this for a local generator if offline rendering
  // is required.
  const qrSrc = `https://api.qrserver.com/v1/create-qr-code/?size=480x480&data=${encodeURIComponent(url)}`;

  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-6 bg-slate-900">
      <h1 className="text-5xl font-light">Scan to pay</h1>
      <p className="font-mono text-7xl">Rs. {amount}</p>
      <img
        src={qrSrc}
        alt="Payment QR code"
        className="rounded-lg bg-white p-4"
        width={480}
        height={480}
      />
      <p className="text-xl text-slate-400">Open your wallet app and scan</p>
    </div>
  );
}
