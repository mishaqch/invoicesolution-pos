import { LegalLayout } from "@/routes/legal";
import { SITE } from "@/lib/site";
import { useSeo } from "@/lib/useSeo";

export default function Privacy() {
  useSeo({
    title: "Privacy Policy",
    description: "How InvoiceSolution collects, uses and protects your data.",
    path: "/privacy",
  });

  return (
    <LegalLayout title="Privacy Policy" updated="June 2026">
      <p>
        This Privacy Policy explains how {SITE.name} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) collects,
        uses and protects information when you visit {SITE.domain} or use our services. By using our
        website or services, you agree to this policy.
      </p>

      <h2>Information we collect</h2>
      <ul>
        <li>Contact details you submit through our forms (name, business name, phone, email, city).</li>
        <li>Business information you share with us during onboarding.</li>
        <li>Basic technical data such as your IP address and browser, used to keep the site secure.</li>
        <li>For customers, the transaction and invoice data processed through our platform on your behalf.</li>
      </ul>

      <h2>How we use information</h2>
      <ul>
        <li>To respond to your enquiries and provide demos and onboarding.</li>
        <li>To deliver, maintain and improve our services.</li>
        <li>To meet legal and tax obligations, including FBR record-retention requirements.</li>
        <li>To communicate with you about your account and relevant updates.</li>
      </ul>

      <h2>Data retention</h2>
      <p>
        Invoice and transaction records are retained for the period required by Pakistani tax law
        (currently six years). Lead and contact information is kept only as long as needed to serve
        you, after which it is deleted or anonymised.
      </p>

      <h2>Sharing</h2>
      <p>
        We do not sell your data. We share information only where necessary to provide our services
        (for example, with FBR/PRAL to fiscalise invoices on your instruction) or where required by
        law.
      </p>

      <h2>Security</h2>
      <p>
        We apply industry-standard safeguards — encryption in transit, access controls and audit
        logging — to protect your information. No system is perfectly secure, but we work hard to
        keep yours safe.
      </p>

      <h2>Your rights</h2>
      <p>
        You can ask us to access, correct or delete your personal information at any time by
        emailing <a href={`mailto:${SITE.email}`}>{SITE.email}</a>.
      </p>

      <h2>Contact</h2>
      <p>
        Questions about this policy? Reach us at <a href={`mailto:${SITE.email}`}>{SITE.email}</a>.
      </p>
    </LegalLayout>
  );
}
