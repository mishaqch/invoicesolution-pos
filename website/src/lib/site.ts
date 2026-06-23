/**
 * Single source of truth for brand + contact constants used across the site.
 * Update once here and it propagates everywhere (header, footer, CTAs, contact).
 */
export const SITE = {
  name: "InvoiceSolution",
  domain: "invoicesolution.pk",
  tagline: "Run your shop. Stay FBR-compliant. Even offline.",
  appUrl: "https://client.invoicesolution.pk",
  // Contact — update these to the real business details before launch.
  email: "info@invoicesolution.pk",
  phoneDisplay: "+92 300 1234567",
  phoneTel: "+923001234567",
  // WhatsApp click-to-chat (international format, no +/spaces).
  whatsapp: "923001234567",
  city: "Lahore, Pakistan",
} as const;

export function whatsappLink(prefill?: string): string {
  const base = `https://wa.me/${SITE.whatsapp}`;
  return prefill ? `${base}?text=${encodeURIComponent(prefill)}` : base;
}
