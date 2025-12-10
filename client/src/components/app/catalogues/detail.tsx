import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Catalogue,
  prettyPrintDate,
  Recipe,
  RecipeDetectionStatus,
  trpc,
} from "@/utils";
import { CookingPot, HelpCircle, Star, Check, ChevronsUpDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "wouter";
import { displayRecipeDetails } from "../recipes/util";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/utils";

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
                  <div className="flex items-center gap-2">
                    <span>
                      {recipe.name || `Recipe #${recipe.id}`}{" "}
                      {recipe.status == RecipeDetectionStatus.SUCCESS
                        ? null
                        : "— Draft"}
                    </span>
                    {recipe.description && (
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <HelpCircle className="h-5 w-5 text-muted-foreground cursor-help" />
                          </TooltipTrigger>
                          <TooltipContent>
                            <p>{recipe.description}</p>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    )}
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
  const { catalogueId } = useParams();
  const [lockedDelete, setLockDelete] = useState(true);
  const [reassignDialogOpen, setReassignDialogOpen] = useState(false);
  const [selectedInstitutionId, setSelectedInstitutionId] = useState<
    number | undefined
  >(undefined);
  const [institutionOpen, setInstitutionOpen] = useState(false);
  const [, navigate] = useLocation();
  const query = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!parseInt(catalogueId || "") }
  );
  const institutionsQuery = trpc.institutions.list.useQuery({
    page: 1,
    limit: 200,
    url: query.data?.url,
  });
  const [institutionSearch, setInstitutionSearch] = useState("");
  const filteredInstitutions = useMemo(() => {
    const term = institutionSearch.trim().toLowerCase();
    if (!term) return institutionsQuery.data?.results || [];
    return (
      institutionsQuery.data?.results.filter((institution) => {
        const inName = institution.name.toLowerCase().includes(term);
        const inDomain = institution.domains.some((d) =>
          d.toLowerCase().includes(term)
        );
        return inName || inDomain;
      }) || []
    );
  }, [institutionSearch, institutionsQuery.data?.results]);
  const destroyMutation = trpc.catalogues.destroy.useMutation();
  const updateInstitutionMutation =
    trpc.catalogues.updateInstitution.useMutation();
  const { toast } = useToast();

  useEffect(() => {
    if (query.data?.institutionId) {
      setSelectedInstitutionId(query.data.institutionId);
    }
  }, [query.data?.institutionId]);

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

  const reassignInstitution = async () => {
    if (!selectedInstitutionId) return;
    try {
      await updateInstitutionMutation.mutateAsync({
        catalogueId: query.data!.id,
        institutionId: selectedInstitutionId,
      });
      await query.refetch();
      toast({
        title: "Institution updated",
        description: "Catalogue institution updated successfully.",
      });
      setReassignDialogOpen(false);
    } catch (error: unknown) {
      const description =
        error instanceof Error ? error.message : JSON.stringify(error);
      toast({
        title: "Unable to update institution",
        description,
      });
    }
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
                <div className="grid gap-3">
                  <Label htmlFor="institution">Institution</Label>
                  <div className="flex items-center gap-3 flex-wrap">
                    {query.data.institution ? (
                      <Link
                        to={`~/institutions/${query.data.institution.id}`}
                        className="font-semibold"
                      >
                        {query.data.institution.name}
                      </Link>
                    ) : (
                      <span className="text-muted-foreground text-sm">
                        Not assigned
                      </span>
                    )}
                    <Dialog
                      open={reassignDialogOpen}
                      onOpenChange={setReassignDialogOpen}
                    >
                      <DialogTrigger asChild>
                        <Button size="sm" variant="outline">
                          Change
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Change institution</DialogTitle>
                          <DialogDescription>
                            Institutions matching the catalogue URL are shown
                            first.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="grid gap-3">
                          <Label>Select institution</Label>
                          <Popover
                            open={institutionOpen}
                            onOpenChange={setInstitutionOpen}
                          >
                            <PopoverTrigger asChild>
                              <Button
                                variant="outline"
                                role="combobox"
                                aria-expanded={institutionOpen}
                                className="justify-between"
                              >
                                {selectedInstitutionId
                                  ? filteredInstitutions.find(
                                      (institution) =>
                                        institution.id === selectedInstitutionId
                                    )?.name || "Select an institution"
                                  : "Select an institution"}
                                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                              </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-[520px] p-0">
                              <Command>
                                <CommandInput
                                  placeholder="Search institutions..."
                                  value={institutionSearch}
                                  onValueChange={setInstitutionSearch}
                                />
                                <CommandList>
                                  <CommandEmpty>
                                    {institutionsQuery.isLoading
                                      ? "Loading institutions..."
                                      : "No institutions found"}
                                  </CommandEmpty>
                                  <CommandGroup>
                                    {filteredInstitutions.map((institution) => (
                                      <CommandItem
                                        key={institution.id}
                                        value={institution.name}
                                        onSelect={() => {
                                          setSelectedInstitutionId(
                                            institution.id
                                          );
                                          setInstitutionOpen(false);
                                        }}
                                      >
                                        <Check
                                          className={cn(
                                            "mr-2 h-4 w-4",
                                            selectedInstitutionId ===
                                              institution.id
                                              ? "opacity-100"
                                              : "opacity-0"
                                          )}
                                        />
                                        <div className="flex flex-col">
                                          <span>{institution.name}</span>
                                          <span className="text-xs text-muted-foreground">
                                            {institution.domains.join(", ")}
                                          </span>
                                        </div>
                                      </CommandItem>
                                    ))}
                                  </CommandGroup>
                                </CommandList>
                              </Command>
                            </PopoverContent>
                          </Popover>
                          <div className="text-xs text-muted-foreground">
                            Can't find it?{" "}
                            <Link to="~/institutions/new">
                              Create a new institution
                            </Link>
                            .
                          </div>
                        </div>
                        <DialogFooter className="gap-2">
                          <Button
                            onClick={reassignInstitution}
                            disabled={
                              !selectedInstitutionId ||
                              updateInstitutionMutation.isLoading
                            }
                          >
                            Save
                          </Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  </div>
                  {query.data.institution?.domains?.length ? (
                    <div className="flex flex-wrap gap-2">
                      {query.data.institution.domains.map((domain) => (
                        <Badge key={domain} variant="secondary">
                          {domain}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
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
                      onCheckedChange={(checked) =>
                        setLockDelete(checked !== true)
                      }
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
