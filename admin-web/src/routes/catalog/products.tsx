import { Plus, Search, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDeleteProduct, useProducts } from "@/lib/queries";

export default function ProductsList() {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useProducts(search ? { search } : {});
  const del = useDeleteProduct();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Products</h1>
        <div className="flex items-center gap-2">
          <Link to="/catalog/products/import">
            <Button variant="outline" size="sm">
              <Upload className="mr-2 h-4 w-4" /> Import CSV
            </Button>
          </Link>
          <Link to="/catalog/products/new">
            <Button size="sm">
              <Plus className="mr-2 h-4 w-4" /> New product
            </Button>
          </Link>
        </div>
      </div>

      <div className="flex max-w-md items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search by SKU, barcode, name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Name</TableHead>
              <TableHead>UoM</TableHead>
              <TableHead className="text-right">Sale price</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            ) : data?.results.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No products yet. Create one or import a CSV.
                </TableCell>
              </TableRow>
            ) : (
              data?.results.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono text-xs">{p.sku}</TableCell>
                  <TableCell>
                    <Link to={`/catalog/products/${p.id}`} className="hover:underline">
                      {p.name}
                    </Link>
                  </TableCell>
                  <TableCell>{p.uom}</TableCell>
                  <TableCell className="text-right font-mono">{p.sale_price}</TableCell>
                  <TableCell>
                    {p.is_active ? (
                      <Badge variant="secondary">Active</Badge>
                    ) : (
                      <Badge variant="outline">Inactive</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => {
                        if (confirm(`Delete ${p.name}?`)) del.mutate(p.id);
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {data && data.count > 0 && (
        <p className="text-xs text-muted-foreground">
          {data.count} product{data.count !== 1 && "s"} total.
        </p>
      )}
    </div>
  );
}
