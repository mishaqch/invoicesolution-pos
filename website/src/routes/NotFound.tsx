import { ButtonAnchor, ButtonLink } from "@/components/ui/Button";
import { SITE } from "@/lib/site";
import { useSeo } from "@/lib/useSeo";

export default function NotFound() {
  useSeo({ title: "Page not found", path: "/404" });
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="absolute inset-0 -z-10 mesh" />
      <div className="container flex min-h-[60vh] flex-col items-center justify-center py-24 text-center">
        <div className="text-7xl font-extrabold tracking-tight text-brand-600 sm:text-8xl">404</div>
        <h1 className="mt-4 text-2xl font-bold text-ink sm:text-3xl">This page wandered off</h1>
        <p className="mt-3 max-w-md text-ink-muted">
          The page you&rsquo;re looking for doesn&rsquo;t exist or may have moved. Let&rsquo;s get you back
          on track.
        </p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <ButtonLink to="/" size="lg">
            Back to home
          </ButtonLink>
          <ButtonAnchor href={SITE.appUrl} variant="secondary" size="lg">
            Customer login
          </ButtonAnchor>
        </div>
      </div>
    </section>
  );
}
