import { Card, IconChip } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { Reveal } from "@/components/ui/Reveal";
import type { Feature } from "@/data/features";

/** Responsive grid of feature cards. Used on Home and Features pages. */
export function FeatureGrid({ features, columns = 4 }: { features: Feature[]; columns?: 3 | 4 }) {
  const cols = columns === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4";
  return (
    <div className={`grid gap-5 sm:grid-cols-2 ${cols}`}>
      {features.map((f, i) => (
        <Reveal key={f.title} delay={(i % 4) * 0.06}>
          <Card className="h-full">
            <IconChip>
              <Icon name={f.icon} className="h-5 w-5" />
            </IconChip>
            <h3 className="text-base font-semibold text-ink">{f.title}</h3>
            <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">{f.desc}</p>
          </Card>
        </Reveal>
      ))}
    </div>
  );
}
