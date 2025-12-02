import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { RecipeDetectionStatus, trpc } from "@/utils";
import { useLocation, useParams } from "wouter";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { useToast } from "@/components/ui/use-toast";
import {
  AlertTriangle,
  Check,
  LoaderIcon,
  Pickaxe,
  RotateCcw,
  Star,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "wouter";
import { displayRecipeDetails } from "./util";
import TestLinkRegex from "./TestLinkRegex";
import { RecipeConfigurationEditor } from "./RecipeConfigurationEditor";
import { CatalogueType, PageType, PaginationConfiguration, UrlPatternType } from "../../../../../common/types";

const PaginationSchema = z.object({
  urlPatternType: z.nativeEnum(UrlPatternType),
  urlPattern: z.string(),
  totalPages: z.number().positive(),
}) as z.ZodType<PaginationConfiguration>;

const RecipeConfigurationSchema: z.ZodType<any> = z.object({
  pageType: z.nativeEnum(PageType),
  linkRegexp: z.string().optional(),
  pagination: PaginationSchema.optional(),
  links: z.lazy(() => RecipeConfigurationSchema).optional(),
  pageLoadWaitTime: z.number().optional().default(0),
});

const FormSchema = z.object({
  name: z.preprocess(
    (val) => (val === "" || val === null ? undefined : val),
    z.string().optional()
  ),
  description: z.preprocess(
    (val) => (val === "" || val === null ? undefined : val),
    z.string().optional()
  ),
  url: z
    .string()
    .url("Catalogue URL must be a valid URL (e.g. https://example.com)."),
  configuration: RecipeConfigurationSchema.optional(),
  isTemplate: z.boolean().optional(),
});

function getFirstLevelRegex(recipe: { configuration?: { linkRegexp?: string } }): string | undefined {
  if (!recipe.configuration) return undefined;
  return recipe.configuration.linkRegexp;
}

function getFirstLevelClickSelector(recipe: { configuration?: { clickSelector?: string; clickOptions?: { limit?: number; waitMs?: number } } }): string | undefined {
  if (!recipe.configuration) return undefined;
  return recipe.configuration.clickSelector;
}

function getFirstLevelClickOptions(recipe: { configuration?: { clickOptions?: { limit?: number; waitMs?: number } } }): { limit?: number; waitMs?: number } | undefined {
  if (!recipe.configuration) return undefined;
  return recipe.configuration.clickOptions;
}

export default function EditRecipe() {
  const [lockedDelete, setLockDelete] = useState(true);
  const [, navigate] = useLocation();
  const { catalogueId, recipeId } = useParams();
  const catalogueQuery = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!catalogueId }
  );
  const recipeQuery = trpc.recipes.detail.useQuery(
    { id: parseInt(recipeId || "") },
    { enabled: !!recipeId }
  );
  const updateRecipe = trpc.recipes.update.useMutation();
  const reconfigureRecipe = trpc.recipes.reconfigure.useMutation();
  const setDefaultRecipe = trpc.recipes.setDefault.useMutation();
  const destroyRecipe = trpc.recipes.destroy.useMutation();
  const { toast } = useToast();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      url: "",
    },
  });
  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    const pollQuery = () => {
      if (recipeQuery.data?.status == RecipeDetectionStatus.SUCCESS) {
        window.clearInterval(intervalRef.current!);
        intervalRef.current = null;
        return;
      }
      recipeQuery.refetch();
    };

    if (!recipeQuery.data) {
      return;
    }

    if (recipeQuery.data.status != RecipeDetectionStatus.SUCCESS) {
      if (!intervalRef.current) {
        intervalRef.current = window.setInterval(pollQuery, 2000);
      } else {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    form.reset({
      ...recipeQuery.data,
      name: recipeQuery.data.name ?? undefined,
      description: recipeQuery.data.description ?? undefined,
    });

    return () => {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [recipeQuery.data]);

  if (!catalogueQuery.data || !recipeQuery.data) {
    return null;
  }

  const catalogue = catalogueQuery.data;
  const recipe = recipeQuery.data;

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    await updateRecipe.mutateAsync({
      id: recipe.id,
      update: {
        name: data.name,
        description: data.description,
        url: data.url,
        configuration: data.configuration,
        isTemplate: data.isTemplate,
      },
    });
    recipeQuery.refetch();
  }

  async function onReconfigure() {
    await reconfigureRecipe.mutateAsync({ id: recipe.id });
    recipeQuery.refetch();
  }

  async function onSetDefault(e: React.MouseEvent<HTMLButtonElement>) {
    e.preventDefault();
    await setDefaultRecipe.mutateAsync({
      id: recipe.id,
    });
    recipeQuery.refetch();
  }

  async function onDestroyRecipe() {
    if (lockedDelete) {
      return;
    }
    await destroyRecipe.mutateAsync({ id: recipe.id });
    toast({
      title: "Recipe deleted",
      description: "The recipe has been deleted successfully.",
    });
    navigate(`/${catalogueId}`);
  }

  const breadCrumbs = [
    { label: "Catalogues", href: "/" },
    { label: catalogueQuery.data.name, href: `/${catalogueId}` },
    {
      label: `Recipe #${recipe.id}`,
      href: `/${catalogueId}/recipes/${recipeId}`,
    },
  ];

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Configure recipe</h1>
      </div>
      <div className="">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="w-full space-y-6"
          >
            <div>
              <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
                <Card>
                  <CardHeader>
                    <CardDescription>Root URL</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <FormField
                      control={form.control}
                      name="name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Recipe Name</FormLabel>
                          <FormControl>
                            <Input placeholder="My Recipe" {...field} />
                          </FormControl>
                          <FormDescription>
                            Optional name for this recipe
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="description"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Description</FormLabel>
                          <FormControl>
                            <Input placeholder="Optional description for this recipe" {...field} />
                          </FormControl>
                          <FormDescription>
                            Optional description that will appear as a tooltip next to the recipe name
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="url"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>URL</FormLabel>
                          <FormControl>
                            <Input placeholder="Catalogue URL" {...field} />
                          </FormControl>
                          <FormDescription>
                            The URL where courses appear
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>
                {recipe.status == RecipeDetectionStatus.SUCCESS ? (
                  <Card>
                    <CardHeader>
                      <CardDescription>Crawling Configuration</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <Tabs defaultValue="editor" className="w-full">
                        <TabsList>
                          <TabsTrigger value="editor">Editor</TabsTrigger>
                          <TabsTrigger value="json">JSON</TabsTrigger>
                        </TabsList>
                        <TabsContent value="editor" className="space-y-4">
                          <RecipeConfigurationEditor
                            control={form.control}
                            setValue={form.setValue}
                            rootUrl={recipe.url}
                            catalogueType={catalogue.catalogueType as CatalogueType}
                          />
                          <div className="flex justify-end pt-4 border-t">
                            <Button
                              type="button"
                              onClick={async () => {
                                const configuration = form.getValues("configuration");
                                try {
                                  await updateRecipe.mutateAsync({
                                    id: recipe.id,
                                    update: {
                                      configuration,
                                    },
                                  });
                                  toast({
                                    title: "Configuration saved",
                                    description: "The recipe configuration has been updated successfully.",
                                  });
                                  recipeQuery.refetch();
                                } catch (err) {
                                  toast({
                                    title: "Error saving configuration",
                                    description: (err as Error).message,
                                    variant: "destructive",
                                  });
                                }
                              }}
                              disabled={
                                recipeQuery.isLoading ||
                                updateRecipe.isLoading ||
                                recipeQuery.data?.status === RecipeDetectionStatus.IN_PROGRESS
                              }
                            >
                              {updateRecipe.isLoading ? (
                                <>
                                  <LoaderIcon className="animate-spin mr-2 h-4 w-4" />
                                  Saving...
                                </>
                              ) : (
                                "Save Configuration"
                              )}
                            </Button>
                          </div>
                        </TabsContent>
                        <TabsContent value="json" className="space-y-4">
                          <div className="text-xs">
                            {displayRecipeDetails(recipe)}
                          </div>
                          <pre className="mt-4 text-xs overflow-x-auto">
                            {JSON.stringify(recipe.configuration, null, 2)}
                          </pre>
                        </TabsContent>
                      </Tabs>
                    </CardContent>
                  </Card>
                ) : null}
              </div>
              {/* Add the Test Link Regex component here, after Crawling Configuration, if recipe.status == SUCCESS */}
              {recipe.status == RecipeDetectionStatus.SUCCESS && (
                <TestLinkRegex
                  defaultUrl={recipe.url}
                  defaultRegex={getFirstLevelRegex(recipe)}
                  clickSelector={getFirstLevelClickSelector(recipe)}
                  clickOptions={getFirstLevelClickOptions(recipe)}
                />
              )}
              {recipe.status == RecipeDetectionStatus.WAITING ? (
                <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
                  <Card>
                    <CardHeader>
                      <CardDescription>Configuration Pending</CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm">
                      <div>
                        <p>
                          Configuration detection hasn't started for this
                          recipe. Please check back later.
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              ) : null}
              {recipe.status == RecipeDetectionStatus.ERROR ? (
                <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
                  <Card>
                    <CardHeader>
                      <CardDescription>Configuration Error</CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm">
                      <div>
                        <p className="text-red-800 font-semibold">
                          CTDL xTRA failed to detect a valid configuration for
                          this recipe.
                        </p>
                        <p className="mt-4">
                          You can adjust the URL, or try again.
                        </p>
                        <p className="mt-8">Failure reason:</p>
                        <pre className="mt-2 text-xs overflow-x-auto">
                          {recipe.detectionFailureReason}
                        </pre>
                        <Button
                          className="mt-8"
                          variant="outline"
                          size="sm"
                          onClick={onReconfigure}
                          disabled={reconfigureRecipe.isLoading}
                        >
                          <RotateCcw className="w-4 h-4 mr-2" />
                          Redetect configuration
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              ) : null}
              {recipe.status != RecipeDetectionStatus.IN_PROGRESS ? (
                <div className="mt-4 grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
                  <Card>
                    <CardHeader>
                      <CardDescription>Settings</CardDescription>
                    </CardHeader>
                    <CardContent className="text-sm">
                      {recipe.status == RecipeDetectionStatus.SUCCESS ? (
                        recipe.isDefault ? (
                          <p className="text-green-800">
                            Default: this recipe is currently set as the default
                            extraction method for the catalogue.
                          </p>
                        ) : (
                          <div>
                            <p>
                              This recipe is not currently set as the default
                              extraction method for the catalogue.
                            </p>
                            <Button
                              className="mt-4"
                              variant="outline"
                              size="sm"
                              onClick={onSetDefault}
                              disabled={setDefaultRecipe.isLoading}
                            >
                              <Star className="w-4 h-4 mr-2" />
                              Set as Default
                            </Button>
                          </div>
                        )
                      ) : null}
                      <div className="mt-4">
                        <FormField
                          control={form.control}
                          name="isTemplate"
                          render={({ field }) => (
                            <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                              <FormControl>
                                <Checkbox
                                  checked={field.value}
                                  onCheckedChange={field.onChange}
                                />
                              </FormControl>
                              <div className="space-y-1 leading-none">
                                <FormLabel>Mark as template</FormLabel>
                                <FormDescription>
                                  Allow this recipe to be reused as a template
                                  when creating new recipes
                                </FormDescription>
                              </div>
                            </FormItem>
                          )}
                        />
                      </div>
                      <div className="mt-4">
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button variant="destructive">Delete recipe</Button>
                          </DialogTrigger>
                          <DialogContent>
                            <DialogHeader>
                              <DialogTitle>
                                Are you absolutely sure?
                              </DialogTitle>
                              <DialogDescription className="pt-2">
                                This action cannot be undone. This will
                                permanently delete the recipe along with its
                                extractions.
                              </DialogDescription>
                            </DialogHeader>
                            <div className="items-top flex space-x-2">
                              <Checkbox
                                id="terms1"
                                onCheckedChange={(e) => setLockDelete(!e)}
                              />
                              <div className="grid gap-1.5 leading-none">
                                <label
                                  htmlFor="terms1"
                                  className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                >
                                  I understand the consequences
                                </label>
                                <p className="text-sm text-muted-foreground">
                                  Permanently delete the recipe and all its data
                                </p>
                                <Button
                                  variant="destructive"
                                  disabled={lockedDelete}
                                  onClick={onDestroyRecipe}
                                  className="mt-4"
                                >
                                  Delete recipe
                                </Button>
                              </div>
                            </div>
                          </DialogContent>
                        </Dialog>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              ) : null}
            </div>

            <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
              <Card>
                <CardHeader>
                  <CardDescription>robots.txt Configuration</CardDescription>
                </CardHeader>
                <CardContent>
                  {recipe.robotsTxt ? (
                    <div className="space-y-4">
                      <div>
                        <p className="text-sm font-medium">Crawling Status</p>
                        <div className="mt-2 flex items-center">
                          {recipe.acknowledgedSkipRobotsTxt ? (
                            <>
                              <AlertTriangle className="h-4 w-4 text-amber-500 mr-2" />
                              <p className="text-sm font-medium text-amber-700">
                                Ignoring robots.txt (acknowledgment provided)
                              </p>
                            </>
                          ) : (
                            <>
                              <Check className="h-4 w-4 text-green-500 mr-2" />
                              <p className="text-sm font-medium text-green-700">
                                Following robots.txt rules
                              </p>
                            </>
                          )}
                        </div>
                      </div>
                      <div>
                        <p className="text-sm font-medium">Rules</p>
                        <div className="mt-2 text-sm">
                          {recipe.robotsTxt.rules
                            .sort((a, b) => {
                              // Sort rules so that user-agent "*" appears first
                              if (a.userAgent === "*" && b.userAgent !== "*")
                                return -1;
                              if (a.userAgent !== "*" && b.userAgent === "*")
                                return 1;
                              return 0;
                            })
                            .map((rule, i) => (
                              <div
                                key={i}
                                className={`mb-4 rounded-md border p-3 ${
                                  rule.userAgent === "*"
                                    ? "bg-blue-50 border-blue-200"
                                    : "bg-muted/50"
                                }`}
                              >
                                <p className="font-medium text-xs text-muted-foreground mb-1">
                                  User-Agent:
                                </p>
                                <p
                                  className={`font-mono mb-2 ${rule.userAgent === "*" ? "font-semibold" : ""}`}
                                >
                                  {rule.userAgent}
                                  {rule.userAgent === "*" && (
                                    <span className="ml-2 text-xs text-blue-600">
                                      (in effect)
                                    </span>
                                  )}
                                </p>
                                {rule.disallow.length > 0 && (
                                  <>
                                    <p className="font-medium text-xs text-muted-foreground mb-1">
                                      Disallow:
                                    </p>
                                    <p className="font-mono mb-2">
                                      {rule.disallow.join(", ")}
                                    </p>
                                  </>
                                )}
                                {rule.allow.length > 0 && (
                                  <>
                                    <p className="font-medium text-xs text-muted-foreground mb-1">
                                      Allow:
                                    </p>
                                    <p className="font-mono mb-2">
                                      {rule.allow.join(", ")}
                                    </p>
                                  </>
                                )}
                                {rule.crawlDelay !== undefined && (
                                  <>
                                    <p className="font-medium text-xs text-muted-foreground mb-1">
                                      Crawl-Delay:
                                    </p>
                                    <p className="font-mono">
                                      {rule.crawlDelay}
                                    </p>
                                  </>
                                )}
                              </div>
                            ))}
                        </div>
                      </div>
                      {recipe.robotsTxt.sitemaps.length > 0 && (
                        <div>
                          <p className="text-sm font-medium">Sitemaps:</p>
                          <div className="rounded-md border p-3 bg-muted/50">
                            {recipe.robotsTxt.sitemaps.map((sitemap, i) => (
                              <p key={i} className="font-mono text-sm mb-1">
                                {sitemap}
                              </p>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm">
                      No robots.txt file found for this website.
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="flex items-center">
              {recipe.status == RecipeDetectionStatus.IN_PROGRESS ? (
                <Button disabled={true} variant={"outline"}>
                  <div className="flex text-sm items-center">
                    <LoaderIcon className="animate-spin mr-2 w-3.5" />
                    Detecting configuration{" "}
                  </div>
                </Button>
              ) : (
                <Button
                  disabled={
                    recipeQuery.isLoading ||
                    updateRecipe.isLoading ||
                    reconfigureRecipe.isLoading ||
                    recipe.status == RecipeDetectionStatus.IN_PROGRESS ||
                    !form.formState.isDirty
                  }
                  type="submit"
                >
                  Save changes
                </Button>
              )}
              {recipe.status == RecipeDetectionStatus.SUCCESS ? (
                <Link
                  className="ml-4"
                  to={`/${catalogue.id}/extract/${recipe.id}`}
                >
                  <Button>
                    <Pickaxe className="h-3.5 w-3.5 mr-2" />
                    Start Extraction
                  </Button>
                </Link>
              ) : null}
            </div>
          </form>
        </Form>
      </div>
    </>
  );
}
