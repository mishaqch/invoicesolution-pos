import { Badge } from "@/components/ui/badge";
import { PageHeader } from "@/components/ui/page-header";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTaxRates } from "@/lib/queries";

export default function TaxRatesList() {
  const { data, isLoading } = useTaxRates();
  return (
    <div className="space-y-4">
      <PageHeader
        title="Tax rates"
        subtitle="Standard rates seeded at tenant creation. Edit via the Django admin until the full edit UI ships."
      />
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead className="text-right">Rate</TableHead>
              <TableHead className="hidden sm:table-cell">Applies to</TableHead>
              <TableHead>Default</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">Loading…</TableCell></TableRow>
            ) : (
              data?.results.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>{t.name}</TableCell>
                  <TableCell className="text-right font-mono">{t.rate}%</TableCell>
                  <TableCell className="hidden capitalize sm:table-cell">{t.applies_to}</TableCell>
                  <TableCell>{t.is_default && <Badge>Default</Badge>}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
