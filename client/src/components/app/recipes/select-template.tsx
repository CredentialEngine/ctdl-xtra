import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatCatalogueType, prettyPrintDate, trpc } from "@/utils";
import { HelpCircle, Search } from "lucide-react";
import { useRef, useState } from "react";
import { useLocation, useParams } from "wouter";

function debounce<T extends (...args: any[]) => any>(
  func: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

export default function SelectTemplate() {
  const { catalogueId } = useParams();
  const [_location, navigate] = useLocation();
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState("");

  const catalogueQuery = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!parseInt(catalogueId || "") }
  );

  const templatesQuery = trpc.recipes.searchTemplates.useQuery(
    {
      searchQuery: debouncedSearchQuery || undefined,
    }
  );

  // Debounce search query - use useRef to ensure the debounced function is stable across renders
  const debouncedSetSearch = useRef(
    debounce((value: string) => {
      setDebouncedSearchQuery(value);
    }, 750)
  ).current;

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    debouncedSetSearch(value);
  };

  const handleSelectTemplate = (recipeId: number) => {
    navigate(`/${catalogueId}/recipes/new?templateId=${recipeId}`);
  };

  if (!catalogueQuery.data) {
    return null;
  }

  const breadCrumbs = [
    { label: "Catalogues", href: "/" },
    { label: catalogueQuery.data.name, href: `/${catalogueId}` },
  ];

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">
          Select Recipe Template
        </h1>
      </div>
      <div className="">
        <Card>
          <CardHeader>
            <CardTitle>Template Recipes</CardTitle>
            <CardDescription>
              Select a template recipe to use as a starting point for creating a
              new recipe. The template configuration will be pre-filled.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search by catalogue name or URL..."
                value={searchQuery}
                onChange={(e) => handleSearchChange(e.target.value)}
                className="pl-9"
              />
            </div>
            {templatesQuery.isLoading ? (
              <div className="text-sm text-muted-foreground">
                Loading templates...
              </div>
            ) : templatesQuery.data && templatesQuery.data.length > 0 ? (
              <div className="max-h-[600px] overflow-y-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Recipe Name</TableHead>
                      <TableHead>Catalogue Name</TableHead>
                      <TableHead>Catalogue Type</TableHead>
                      <TableHead>Catalogue URL</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead>Extractions</TableHead>
                      <TableHead>Last Extraction</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {templatesQuery.data.map((item) => (
                      <TableRow key={item.recipe.id}>
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            <span>{item.recipe.name || `Recipe #${item.recipe.id}`}</span>
                            {item.recipe.description && (
                              <TooltipProvider>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <HelpCircle className="h-5 w-5 text-muted-foreground cursor-help" />
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    <p>{item.recipe.description}</p>
                                  </TooltipContent>
                                </Tooltip>
                              </TooltipProvider>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>{item.catalogue.name}</TableCell>
                        <TableCell>
                          {formatCatalogueType(item.catalogue.catalogueType)}
                        </TableCell>
                        <TableCell className="font-mono text-xs">
                          {item.catalogue.url}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {prettyPrintDate(item.recipe.createdAt)}
                        </TableCell>
                        <TableCell>{item.extractionCount}</TableCell>
                        <TableCell className="text-muted-foreground">
                          {item.mostRecentExtractionDate
                            ? prettyPrintDate(item.mostRecentExtractionDate)
                            : "Never"}
                        </TableCell>
                        <TableCell>
                          <Button
                            size="sm"
                            onClick={() => handleSelectTemplate(item.recipe.id)}
                          >
                            Select
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                {debouncedSearchQuery
                  ? "No templates found matching your search."
                  : "No template recipes available. Create a recipe and mark it as a template to use it here."}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

