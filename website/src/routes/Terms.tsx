import { LegalLayout } from "@/routes/legal";
import { SITE } from "@/lib/site";
import { useSeo } from "@/lib/useSeo";

export default function Terms() {
  useSeo({
    title: "Terms of Service",
    description: "The terms that govern your use of InvoiceSolution.",
    path: "/terms",
  });

  return (
    <LegalLayout title="Terms of Service" updated="June 2026">
      <p>
        These Terms of Service govern your use of {SITE.name} and the {SITE.domain} website. By using
        our services, you agree to these terms.
      </p>

      <h2>The service</h2>
      <p>
        {SITE.name} provides Point of Sale and Digital Invoicing software that integrates with FBR
        Digital Invoicing through a licensed integration. We are an independent software provider and
        are not a government body. While we work to keep invoices compliant, you remain responsible
        for the accuracy of the data you enter and for your own tax obligations.
      </p>

      <h2>Accounts</h2>
      <ul>
        <li>Accounts are provisioned by our team during onboarding.</li>
        <li>You are responsible for keeping your login credentials secure.</li>
        <li>You must provide accurate business and FBR information.</li>
      </ul>

      <h2>Subscriptions &amp; payment</h2>
      <ul>
        <li>Subscriptions are billed per the plan you choose (monthly or yearly), in PKR.</li>
        <li>New accounts may include a trial period; details are confirmed at onboarding.</li>
        <li>Fees charged directly by FBR/PRAL to your business are separate from our subscription.</li>
      </ul>

      <h2>Acceptable use</h2>
      <p>
        You agree not to misuse the service, attempt to disrupt it, or use it for any unlawful
        purpose. We may suspend access where these terms are breached.
      </p>

      <h2>Availability</h2>
      <p>
        We aim for high availability, and the POS terminal is designed to keep working offline.
        However, we do not guarantee uninterrupted service and are not liable for losses arising from
        downtime, third-party services, or events beyond our reasonable control.
      </p>

      <h2>Limitation of liability</h2>
      <p>
        To the maximum extent permitted by law, our liability is limited to the amount you paid for
        the service in the preceding three months. We are not liable for indirect or consequential
        losses.
      </p>

      <h2>Changes</h2>
      <p>
        We may update these terms from time to time. Continued use of the service after changes take
        effect constitutes acceptance of the updated terms.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about these terms? Email <a href={`mailto:${SITE.email}`}>{SITE.email}</a>.
      </p>
    </LegalLayout>
  );
}
