import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import {
  Catalogue,
  prettyPrintDate,
  Recipe,
  RecipeDetectionStatus,
  trpc,
} from "@/utils";
import { CookingPot, Star } from "lucide-react";
import { useState } from "react";
import { Link, useLocation, useParams } from "wouter";
import { displayRecipeDetails } from "../recipes/util";

interface RecipeListProps {
  catalogue: Catalogue;
}

const RecipeList = ({ catalogue }: RecipeListProps) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recipes</CardTitle>
      </CardHeader>
      <CardContent>
        <Link to={`/${catalogue.id}/recipes/new`}>
          <Button variant={catalogue.recipes.length ? "outline" : "default"}>
            <CookingPot className="w-4 h-4 mr-2" />
            Configure New Recipe
          </Button>
        </Link>
        {catalogue.recipes.length ? (
          <div className="grid">
            {catalogue.recipes.map((recipe) => (
              <Link
                key={`/${catalogue.id}/recipes/${recipe.id}`}
                to={`/${catalogue.id}/recipes/${recipe.id}`}
                className="hover:bg-muted py-2 px-4 border mt-4 rounded-md flex items-center justify-between"
              >
                <div className="text-xs">
                  <div>
                    Recipe #{recipe.id}{" "}
                    {recipe.status == RecipeDetectionStatus.SUCCESS
                      ? null
                      : "— Draft"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {displayRecipeDetails(recipe as Recipe)}
                  </div>
                </div>
                {recipe.isDefault ? (
                  <div>
                    <Star />
                  </div>
                ) : null}
              </Link>
            ))}
          </div>
        ) : (
          <div className="text-xs justify-normal mt-4">
            <p>Configure a recipe to start extracting data.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default function CatalogueDetail() {
  let { catalogueId } = useParams();
  const [lockedDelete, setLockDelete] = useState(true);
  const [_location, navigate] = useLocation();
  const query = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!parseInt(catalogueId || "") }
  );
  const destroyMutation = trpc.catalogues.destroy.useMutation();
  const { toast } = useToast();

  if (!query.data) {
    return null;
  }

  const destroyCatalogue = async () => {
    if (lockedDelete) {
      return;
    }
    await destroyMutation.mutateAsync({ id: query.data!.id });
    toast({
      title: "Catalogue deleted",
      description: "The catalogue has been deleted successfully.",
    });
    navigate("/");
  };

  return (
    <>
      <div className="grid gap-4 md:grid-cols-[1fr_250px] lg:grid-cols-3 lg:gap-8">
        <div className="grid auto-rows-max items-start gap-4 lg:col-span-2 lg:gap-8">
          <Card>
            <CardHeader>
              <CardTitle>Catalogue Details</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-6">
                <div className="grid gap-3">
                  <Label htmlFor="description">URL</Label>
                  <Input
                    id="description"
                    type="text"
                    className="w-full"
                    defaultValue={query.data.url}
                  />
                </div>
                <div className="grid gap-3">
                  <Label htmlFor="name">Name</Label>
                  <Input
                    id="name"
                    type="text"
                    className="w-full"
                    defaultValue={query.data.name}
                  />
                </div>
                <div className="grid gap-3">
                  <Label htmlFor="type">Type</Label>
                  <Badge variant="outline">{query.data.catalogueType}</Badge>
                </div>
                {query.data.thumbnailUrl ? (
                  <div>
                    <img
                      src={query.data.thumbnailUrl}
                      style={{ maxHeight: "30px" }}
                    />
                  </div>
                ) : null}
              </div>
              {/*
TODO: add save
              <Button variant="outline" type="submit" className="mt-4">
                Save
              </Button>
              */}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Extractions</CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Recipe</TableHead>
                    <TableHead>Created At</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {query.data.extractions.map((extraction) => (
                    <TableRow key={`extractions-${extraction.id}`}>
                      <TableCell>
                        <Link to={`~/extractions/${extraction.id}`}>
                          #{extraction.id}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link to={`~/extractions/${extraction.id}`}>
                          #{extraction.recipeId}
                        </Link>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {prettyPrintDate(extraction.createdAt)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
        <div className="grid auto-rows-max items-start gap-4 lg:gap-8">
          <RecipeList catalogue={query.data} />
          <Card>
            <CardHeader>
              <CardTitle>Settings</CardTitle>
            </CardHeader>
            <CardContent>
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="destructive">Delete catalogue</Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>Are you absolutely sure?</DialogTitle>
                    <DialogDescription className="pt-2">
                      This action cannot be undone. This will permanently delete
                      the catalogue along with its recipes and extracted data.
                    </DialogDescription>
                  </DialogHeader>
                  <div className="items-top flex space-x-2">
                    <Checkbox
                      id="terms1"
                      onCheckedChange={(e) => setLockDelete(!!!e)}
                    />
                    <div className="grid gap-1.5 leading-none">
                      <label
                        htmlFor="terms1"
                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                      >
                        I understand the consequences
                      </label>
                      <p className="text-sm text-muted-foreground">
                        Permanently delete the catalogue and all its data
                      </p>
                      <Button
                        variant="destructive"
                        disabled={lockedDelete}
                        onClick={destroyCatalogue}
                        className="mt-4"
                      >
                        Delete catalogue
                      </Button>
                    </div>
                  </div>
                </DialogContent>
              </Dialog>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
