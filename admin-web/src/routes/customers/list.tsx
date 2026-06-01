import { Plus, Search, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCustomers } from "@/lib/queries";

function formatRs(amount: string): string {
  const n = Number(amount);
  if (Number.isNaN(n)) return amount;
  return `Rs. ${n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function CustomersList() {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useCustomers({ search });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Customers</h1>
          <p className="text-sm text-muted-foreground">
            {isLoading ? "Loading…" : `${data?.count ?? 0} customers`}
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline">
            <Link to="/customers/import">
              <Upload className="mr-1 h-4 w-4" /> Import CSV
            </Link>
          </Button>
          <Button asChild>
            <Link to="/customers/new">
              <Plus className="mr-1 h-4 w-4" /> New customer
            </Link>
          </Button>
        </div>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder="Search by name, phone, CNIC, NTN"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search customers"
        />
      </div>

      <Card>
        <CardContent className="overflow-x-auto p-0">
          {!data || data.results.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground">
              {search ? "No matches." : "No customers yet — add one to start tracking credit and store credit."}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-left font-medium">Name</th>
                  <th className="px-3 py-2 text-left font-medium">Phone</th>
                  <th className="px-3 py-2 text-left font-medium">Type</th>
                  <th className="px-3 py-2 text-right font-medium">Balance</th>
                  <th className="px-3 py-2 text-right font-medium">Store credit</th>
                  <th className="px-3 py-2 text-right font-medium">Loyalty</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((c) => (
                  <tr key={c.id} className="border-b hover:bg-muted/30">
                    <td className="px-3 py-2">
                      <Link to={`/customers/${c.id}`} className="font-medium hover:underline">
                        {c.name}
                      </Link>
                      {c.customer_code && (
                        <span className="ml-2 text-xs text-muted-foreground">{c.customer_code}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{c.phone || ""}</td>
                    <td className="px-3 py-2">
                      <Badge variant={c.registration_type === "registered" ? "default" : "secondary"}>
                        {c.registration_type}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-right font-mono">{formatRs(c.current_balance)}</td>
                    <td className="px-3 py-2 text-right font-mono">{formatRs(c.store_credit)}</td>
                    <td className="px-3 py-2 text-right">{c.loyalty_points}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
