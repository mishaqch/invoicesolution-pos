/**
 * Single source of truth for brand + contact constants used across the site.
 * Update once here and it propagates everywhere (header, footer, CTAs, contact).
 */
export const SITE = {
    name: "InvoiceSolution",
    domain: "invoicesolution.pk",
    tagline: "Run your shop. Stay FBR-compliant. Even offline.",
    appUrl: "https://client.invoicesolution.pk",
    // Contact — real business details.
    email: "info@invoicesolution.pk",
    phoneDisplay: "0300 5066442",
    phoneTel: "+923005066442",
    // WhatsApp click-to-chat (international format, no +/spaces).
    whatsapp: "923005066442",
    city: "Lahore, Pakistan",
};
export function whatsappLink(prefill) {
    const base = `https://wa.me/${SITE.whatsapp}`;
    return prefill ? `${base}?text=${encodeURIComponent(prefill)}` : base;
}
