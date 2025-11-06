import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { formatCatalogueType, prettyPrintDate, trpc } from "@/utils";
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { HelpCircle, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  CatalogueType,
  PageType,
  PaginationConfiguration,
  UrlPatternType,
} from "../../../../../common/types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import TestLinkRegex from "./TestLinkRegex";
import { RecipeLevel, FormRecipeConfiguration } from "./RecipeLevel";

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

const PaginationSchema = z.object({
  urlPatternType: z.nativeEnum(UrlPatternType),
  urlPattern: z.string().url(),
  totalPages: z.number().positive(),
}) as z.ZodType<PaginationConfiguration>;

const RecipeConfigurationSchema: z.ZodType<FormRecipeConfiguration> = z.object({
  pageType: z.nativeEnum(PageType),
  linkRegexp: z.string().optional(),
  pagination: PaginationSchema.optional(),
  links: z.lazy(() => RecipeConfigurationSchema).optional(),
  pageLoadWaitTime: z.number().optional().default(0),
});

const FormSchema = z.object({
  name: z.string().optional(),
  description: z.string().optional(),
  url: z
    .string()
    .url("Catalogue URL must be a valid URL (e.g. https://example.com)."),
  manualConfig: z.boolean().default(false),
  configuration: RecipeConfigurationSchema.optional(),
  acknowledgedSkipRobotsTxt: z.boolean().default(false),
  creationMode: z.enum(["detect", "manual", "template"]).default("detect"),
});

export default function CreateRecipe() {
  const { catalogueId } = useParams();
  const searchParams = new URLSearchParams(window.location.search);
  const templateIdFromUrl = searchParams.get("templateId");
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(
    templateIdFromUrl ? parseInt(templateIdFromUrl) : null
  );
  const [templateSearchQuery, setTemplateSearchQuery] = useState("");
  const [debouncedTemplateSearchQuery, setDebouncedTemplateSearchQuery] = useState("");

  const catalogueQuery = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!parseInt(catalogueId || "") }
  );
  const templateQuery = trpc.recipes.detail.useQuery(
    { id: selectedTemplateId! },
    { enabled: !!selectedTemplateId }
  );
  const templatesQuery = trpc.recipes.searchTemplates.useQuery(
    {
      searchQuery: debouncedTemplateSearchQuery || undefined,
    }
  );

  // Debounce template search query
  const debouncedSetTemplateSearch = useRef(
    debounce((value: string) => {
      setDebouncedTemplateSearchQuery(value);
    }, 750)
  ).current;

  const handleTemplateSearchChange = (value: string) => {
    setTemplateSearchQuery(value);
    debouncedSetTemplateSearch(value);
  };
  const createRecipe = trpc.recipes.create.useMutation();
  const detectPagination = trpc.recipes.detectPagination.useMutation();
  const detectUrlRegexp = trpc.recipes.detectUrlRegexp.useMutation();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    mode: "onSubmit",
    reValidateMode: "onSubmit",
    defaultValues: {
      url: "",
      manualConfig: false,
      acknowledgedSkipRobotsTxt: false,
      creationMode: templateIdFromUrl ? "template" : "detect",
    },
  });
  const { toast } = useToast();
  const [_location, navigate] = useLocation();

  useEffect(() => {
    if (!catalogueQuery.data) {
      return;
    }
    if (templateQuery.data && selectedTemplateId) {
      // Pre-fill form with template data
      form.reset({
        url: catalogueQuery.data.url,
        manualConfig: true,
        configuration: templateQuery.data.configuration as any,
        acknowledgedSkipRobotsTxt: templateQuery.data.acknowledgedSkipRobotsTxt || false,
        creationMode: "template" as const,
        name: templateQuery.data.name || undefined,
        description: templateQuery.data.description || undefined,
      }, { keepErrors: false });
    } else if (form.getValues("creationMode") === "template") {
      // If we're in template mode but no template is selected, keep template mode
      // but reset URL to catalogue URL
      form.reset({
        url: catalogueQuery.data.url,
        creationMode: "template" as const,
        manualConfig: false,
        acknowledgedSkipRobotsTxt: false,
      });
    } else {
      form.reset({ url: catalogueQuery.data.url });
    }
  }, [catalogueQuery.data, templateQuery.data, selectedTemplateId]);

  const creationMode = form.watch("creationMode");

  useEffect(() => {
    if (creationMode === "manual" || creationMode === "template") {
      if (!form.getValues("configuration")) {
        form.setValue("configuration", {
          pageType: PageType.DETAIL,
        });
      }
      form.setValue("manualConfig", true);
    } else {
      form.setValue("manualConfig", false);
      if (creationMode === "detect") {
        form.setValue("configuration", undefined);
      }
    }
  }, [creationMode, form]);

  if (!catalogueQuery.data) {
    return null;
  }

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    try {
      // Explicitly prevent submission in template mode without a valid configuration
      if (creationMode === "template") {
        if (!selectedTemplateId) {
          toast({
            title: "Template required",
            description: "Please select a template recipe before creating the recipe.",
            variant: "destructive",
          });
          return;
        }
        if (!data.configuration || !data.configuration.pageType) {
          toast({
            title: "Configuration required",
            description: "Template configuration is missing. Please select a template or wait for it to load.",
            variant: "destructive",
          });
          return;
        }
      }

      // Ensure manual mode also has configuration
      if (creationMode === "manual" && (!data.configuration || !data.configuration.pageType)) {
        toast({
          title: "Configuration required",
          description: "Please provide a valid recipe configuration.",
          variant: "destructive",
        });
        return;
      }

      const result = await createRecipe.mutateAsync({
        catalogueId: parseInt(catalogueId!),
        url: data.url,
        name: data.name,
        description: data.description,
        configuration:
          creationMode === "template" || creationMode === "manual"
            ? data.configuration
            : undefined,
        acknowledgedSkipRobotsTxt: data.acknowledgedSkipRobotsTxt,
      });
      if (result.context?.message) {
        toast({
          title: "Configuration detection issue",
          description: result.context.message,
        });
      }
      navigate(`/${catalogueId}/recipes/${result.id}`);
    } catch (err) {
      toast({
        description: (err as Error).message,
        variant: "destructive",
      });
    }
  }

  const breadCrumbs = [
    { label: "Catalogues", href: "/" },
    { label: catalogueQuery.data.name, href: `/${catalogueId}` },
  ];

  const configuration = form.watch("configuration");

  async function onDetectPagination(
    // @ts-ignore
    rootUrl: string,
    // @ts-ignore
    context: {
      parents?: FormRecipeConfiguration[];
      current: FormRecipeConfiguration;
    },
    formPath?: string
  ) {
    if (!catalogueQuery.data?.catalogueType) return;
    try {
      const url = context.parents
        ? context.parents[context.parents.length - 1]?.sampleUrls![0]
        : rootUrl;
      const result = await detectPagination.mutateAsync({
        url,
        catalogueType: catalogueQuery.data.catalogueType as CatalogueType,
      });
      if (result) {
        const paginationPath = formPath
          ? `${formPath}.pagination`
          : "configuration.pagination";
        form.setValue(
          `${paginationPath}.urlPatternType` as any,
          result.urlPatternType
        );
        form.setValue(`${paginationPath}.urlPattern` as any, result.urlPattern);
        form.setValue(`${paginationPath}.totalPages` as any, result.totalPages);
      }
    } catch (err) {
      toast({
        description: (err as Error).message,
      });
    }
  }

  async function onDetectUrlRegexp(
    rootUrl: string,
    context: {
      parents?: FormRecipeConfiguration[];
      current: FormRecipeConfiguration;
    },
    formPath?: string
  ) {
    if (!catalogueQuery.data?.catalogueType) return;
    try {
      const urls = context.parents
        ? context.parents[context.parents.length - 1]?.sampleUrls!.slice(0, 2)
        : [rootUrl];
      const result = await detectUrlRegexp.mutateAsync({
        urls,
        pageType: context.current.pageType,
        catalogueType: catalogueQuery.data.catalogueType as CatalogueType,
      });
      if (result) {
        if (formPath) {
          form.setValue(`${formPath}.linkRegexp` as any, result.regexp);
        } else {
          form.setValue("configuration.linkRegexp" as any, result.regexp);
        }

        if (result.urls) {
          if (formPath) {
            form.setValue(
              `${formPath}.sampleUrls` as any,
              result.urls.slice(0, 10)
            );
          } else {
            form.setValue(
              "configuration.sampleUrls" as any,
              result.urls.slice(0, 10)
            );
          }
        }
      }
    } catch (err) {
      toast({
        description: (err as Error).message,
      });
    }
  }

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Configure recipe</h1>
      </div>
      <div className="w-full">
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="w-full space-y-6"
          >
            <div>
              <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-1 lg:gap-4">
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
                    <FormField
                      control={form.control}
                      name="creationMode"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Configuration Method</FormLabel>
                          <Select
                            onValueChange={(value) => {
                              field.onChange(value);
                              if (value === "manual") {
                                // Immediately set configuration so the Recipe Configuration section appears
                                if (!form.getValues("configuration")) {
                                  form.setValue("configuration", {
                                    pageType: PageType.DETAIL,
                                  });
                                }
                                form.setValue("manualConfig", true);
                                setSelectedTemplateId(null);
                              } else if (value === "detect") {
                                form.setValue("manualConfig", false);
                                form.setValue("configuration", undefined);
                                setSelectedTemplateId(null);
                              }
                              // For "template", we don't navigate - just show the template selection card
                            }}
                            value={field.value}
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue defaultValue="detect" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="detect">Auto-detect</SelectItem>
                              <SelectItem value="manual">Manual</SelectItem>
                              <SelectItem value="template">From template</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormDescription>
                            {creationMode === "detect"
                              ? "Automatically detect recipe configuration using AI"
                              : creationMode === "manual"
                                ? "Manually configure the recipe"
                                : "Use an existing recipe as a template"}
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="acknowledgedSkipRobotsTxt"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                          <FormControl>
                            <Checkbox
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                          <div className="space-y-1 leading-none">
                            <FormLabel>Bypass robots.txt</FormLabel>
                            <FormDescription>
                              I confirm we have permission from the website
                              owners to bypass robots.txt restrictions.
                            </FormDescription>
                          </div>
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>
              </div>
            </div>

            {creationMode === "template" && (
              <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-1 lg:gap-4">
                <Card>
                  <CardHeader>
                    <CardDescription>Select Template Recipe</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {selectedTemplateId && templateQuery.data ? (
                      <div className="rounded-md bg-muted p-3 text-sm">
                        <p className="font-medium">Using template: Recipe #{templateQuery.data.id}</p>
                        <p className="text-muted-foreground mt-1">
                          Configuration from template will be pre-filled below.
                        </p>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          className="mt-2"
                          onClick={() => {
                            setSelectedTemplateId(null);
                            // Ensure creation mode stays as template
                            form.setValue("creationMode", "template");
                          }}
                        >
                          Change Template
                        </Button>
                      </div>
                    ) : (
                      <>
                        <div className="relative">
                          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                          <Input
                            placeholder="Search by catalogue name or URL..."
                            value={templateSearchQuery}
                            onChange={(e) => handleTemplateSearchChange(e.target.value)}
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
                                                <HelpCircle className="h-8 w-8 text-muted-foreground cursor-help" />
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
                                        type="button"
                                        size="sm"
                                        onClick={() => setSelectedTemplateId(item.recipe.id)}
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
                            {debouncedTemplateSearchQuery
                              ? "No templates found matching your search."
                              : "No template recipes available. Create a recipe and mark it as a template to use it here."}
                          </div>
                        )}
                      </>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}

            {((creationMode === "template" && selectedTemplateId) || creationMode === "manual") && (
              <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-1 lg:gap-4">
                <Card>
                  <CardHeader>
                    <CardDescription>Recipe Configuration</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <FormField
                      control={form.control}
                      name="configuration.pageLoadWaitTime"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Page Load Wait Time (seconds)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              placeholder="0"
                              {...field}
                              onChange={(e) => {
                                const value = e.target.value ? parseInt(e.target.value) : undefined;
                                field.onChange(value);
                              }}
                              value={field.value ?? ""}
                            />
                          </FormControl>
                          <FormDescription>
                            How long to wait (in seconds) for the page to fully load after opening. This is useful for pages that dynamically load content. Leave empty or 0 for no additional wait.
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    {configuration && (
                      <RecipeLevel
                        path="configuration"
                        control={form.control}
                        onDetectUrlRegexp={onDetectUrlRegexp}
                        onDetectPagination={onDetectPagination}
                      />
                    )}

                    <TestLinkRegex
                      simplified
                      defaultUrl={form.watch("url")}
                      defaultRegex={configuration?.linkRegexp}
                    />
                  </CardContent>
                </Card>
              </div>
            )}

            <div className="flex items-center">
              <Button disabled={createRecipe.isLoading} type="submit">
                Next
              </Button>
            </div>
          </form>
        </Form>
      </div>
    </>
  );
}
