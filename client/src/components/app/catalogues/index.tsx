import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Recipe, RecipeDetectionStatus, trpc } from "@/utils";
import { CookingPot, Pickaxe, Plus } from "lucide-react";
import { Link } from "wouter";
import { Button } from "../../ui/button";
import usePagination from "../usePagination";

const CatalogueListItem = (catalogue: {
  id: number;
  name: string;
  url: string;
  catalogueType: string;
  thumbnailUrl?: string | null;
  recipes: Recipe[];
}) => {
  const hasReadyRecipe = catalogue.recipes.some(
    (r) => r.status == RecipeDetectionStatus.SUCCESS
  );

  return (
    <TableRow>
      <TableCell className="font-medium">
        <Link to={`/${catalogue.id}`}>
          <div className="flex items-center gap-4">
            {catalogue.thumbnailUrl ? (
              <img src={catalogue.thumbnailUrl} style={{ maxHeight: "30px" }} />
            ) : null}
            {catalogue.name}
          </div>
        </Link>
      </TableCell>
      <TableCell className="hidden md:table-cell">
        <Badge variant="outline">{catalogue.catalogueType}</Badge>
      </TableCell>
      <TableCell className="hidden md:table-cell">
        {hasReadyRecipe ? (
          <Link to={`/${catalogue.id}/extract`}>
            <Button size="sm" className="text-sm">
              <Pickaxe className="h-3.5 w-3.5 mr-2" />
              Extract
            </Button>
          </Link>
        ) : (
          <Link to={`/${catalogue.id}/recipes/new`}>
            <Tooltip delayDuration={100}>
              <TooltipTrigger asChild>
                <Button variant="outline" size="sm" className="text-sm">
                  <CookingPot className="h-3.5 w-3.5 mr-2" />
                  Configure recipe
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Configure a recipe to start extracting data.</p>
              </TooltipContent>
            </Tooltip>
          </Link>
        )}
      </TableCell>
    </TableRow>
  );
};

export default function Catalogues() {
  const { page, PaginationButtons } = usePagination();
  const listQuery = trpc.catalogues.list.useQuery({ page });

  if (listQuery.isFetched && !listQuery.data?.results.length) {
    return (
      <>
        <div className="flex items-center">
          <h1 className="text-lg font-semibold md:text-2xl">Catalogues</h1>
        </div>
        <div
          className="flex flex-1 items-center justify-center rounded-lg border border-dashed shadow-sm"
          x-chunk="dashboard-02-chunk-1"
        >
          <div className="flex flex-col items-center gap-1 text-center">
            <h3 className="text-2xl font-bold tracking-tight">
              You haven't configured any catalogues yet!
            </h3>
            <p className="text-sm text-muted-foreground">
              You can start extracting data as soon as you configure one.
            </p>
            <Link to="/new">
              <Button className="mt-4">Add Catalogue</Button>
            </Link>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="w-full flex justify-between items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Catalogues</h1>
        <Link to={"/new"}>
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Add catalogue
          </Button>
        </Link>
      </div>
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead colSpan={3}>Catalogue</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {listQuery.data?.results.map((catalogue) => (
                <CatalogueListItem key={catalogue.url} {...catalogue} />
              )) || (
                <TableRow>
                  <TableCell colSpan={2}>
                    <div className="flex items-center justify-center">
                      <span className="text-muted-foreground">
                        Loading catalogues...
                      </span>
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
        {listQuery.data?.results.length ? (
          <CardFooter>
            <PaginationButtons
              totalItems={listQuery.data.totalItems}
              totalPages={listQuery.data.totalPages}
            />
          </CardFooter>
        ) : null}
      </Card>
    </>
  );
}
