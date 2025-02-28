import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { prettyPrintDate, trpc } from "@/utils";
import { Earth, List } from "lucide-react";
import { Link, useParams } from "wouter";
import usePagination from "../usePagination";

export default function DatasetDetail() {
  const { catalogueId } = useParams();
  const { page, PaginationButtons } = usePagination();
  const catalogueQuery = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!catalogueId }
  );
  const datasetsQuery = trpc.catalogues.datasets.useQuery(
    { id: parseInt(catalogueId || ""), page },
    { enabled: !!catalogueId }
  );

  if (!datasetsQuery.data?.results.length) {
    return null;
  }

  const catalogue = catalogueQuery.data!;
  const datasets = datasetsQuery.data.results;

  return (
    <>
      <h1 className="text-lg font-semibold md:text-2xl">
        Data Library for Catalogue
      </h1>
      <Link to={`~/catalogues/${catalogue.id}`}>
        <div className="border p-6">
          <div className="text-sm text-muted-foreground">Catalogue Details</div>
          <div className="mt-4 flex items-center gap-4">
            <Earth />
            {catalogue.thumbnailUrl ? (
              <div>
                <img
                  src={catalogue.thumbnailUrl}
                  style={{ maxHeight: "25px" }}
                />
              </div>
            ) : null}
            <h1>{catalogue.name}</h1>
          </div>
        </div>
      </Link>
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Extraction</TableHead>
                <TableHead>Created At</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Items</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {datasets.map((dataset) => (
                <TableRow key={`dataset-${dataset.id}`}>
                  <TableCell>#{dataset.id}</TableCell>
                  <TableCell>{prettyPrintDate(dataset.createdAt)}</TableCell>
                  <TableCell>{catalogue.catalogueType}</TableCell>
                  <TableCell>
                    <Button
                      variant={"outline"}
                      size="sm"
                      className="text-xs"
                      asChild
                    >
                      <Link to={`/items/${dataset.id}`}>
                        <List className="w-3.5 h-3.5 mr-2" />
                        View {dataset.itemsCount} items
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              )) || (
                <TableRow>
                  <TableCell colSpan={3}>
                    <div className="flex items-center justify-center">
                      <span className="text-muted-foreground">
                        Loading extractions...
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
        {datasets.length ? (
          <CardFooter>
            <PaginationButtons
              totalItems={datasetsQuery.data.totalItems}
              totalPages={datasetsQuery.data.totalPages}
            />
          </CardFooter>
        ) : null}
      </Card>
    </>
  );
}
