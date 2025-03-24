import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { trpc } from "@/utils";
import { useLocation, useParams } from "wouter";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useFormContext } from "react-hook-form";
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
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import {
  CatalogueType,
  PageType,
  PaginationConfiguration,
  UrlPatternType,
} from "../../../../../common/types";

type FormRecipeConfiguration = {
  pageType: PageType;
  linkRegexp?: string;
  pagination?: PaginationConfiguration;
  links?: any;
  sampleUrls?: string[];
};

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
});

const FormSchema = z.object({
  url: z
    .string()
    .url("Catalogue URL must be a valid URL (e.g. https://example.com)."),
  manualConfig: z.boolean().default(false),
  configuration: RecipeConfigurationSchema.optional(),
});

function RecipeLevel({
  path,
  control,
  onDetectUrlRegexp,
  onDetectPagination,
}: {
  path: string;
  control: any;
  onDetectUrlRegexp: (
    rootUrl: string,
    context: {
      parents?: FormRecipeConfiguration[];
      current: FormRecipeConfiguration;
    },
    formPath?: string
  ) => Promise<void>;
  onDetectPagination: (
    rootUrl: string,
    context: {
      parents?: FormRecipeConfiguration[];
      current: FormRecipeConfiguration;
    },
    formPath?: string
  ) => Promise<void>;
}) {
  const form = useFormContext<z.infer<typeof FormSchema>>();
  const config = form.watch(path as any) as any as FormRecipeConfiguration;
  const [isDetectingUrlRegexp, setIsDetectingUrlRegexp] = useState(false);
  const [isDetectingPagination, setIsDetectingPagination] = useState(false);

  const rootUrl = form.watch("url");

  const currentConfig = form.getValues(
    path as any
  ) as any as FormRecipeConfiguration;
  const parts = path.split(".");
  const parentsConfig =
    parts.length > 1
      ? parts.slice(0, -1).reduce((acc, _, index) => {
          const parentPath = parts.slice(0, index + 1).join(".");
          return [...acc, form.getValues(parentPath as any)];
        }, [] as FormRecipeConfiguration[])
      : undefined;
  const canDetectUrlRegexp =
    !isDetectingUrlRegexp &&
    (!parentsConfig ||
      parentsConfig.length === 0 ||
      parentsConfig[parentsConfig.length - 1]?.sampleUrls?.length);

  return (
    <div className="space-y-4 border-l-2 pl-4 mt-4">
      <FormField
        control={control}
        name={`${path}.pageType` as any}
        render={({ field }) => (
          <FormItem>
            <FormLabel>Page Type</FormLabel>
            <Select
              onValueChange={(value) => {
                const currentConfig = form.getValues(
                  path as any
                ) as any as FormRecipeConfiguration;
                const links =
                  PageType.DETAIL_LINKS == value
                    ? { pageType: PageType.DETAIL }
                    : currentConfig?.links;
                (form.setValue as any)(path, {
                  ...currentConfig,
                  pageType: value as PageType,
                  ...(value !== PageType.DETAIL && {
                    linkRegexp: currentConfig?.linkRegexp || "",
                    pagination: currentConfig?.pagination,
                    links: links,
                  }),
                });
              }}
              defaultValue={field.value}
            >
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder="Select a page type" />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {Object.values(PageType).map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />

      {config?.pageType && config.pageType !== PageType.DETAIL && (
        <>
          <FormField
            control={control}
            name={`${path}.linkRegexp`}
            render={({ field }) => (
              <FormItem>
                <FormLabel>Link RegExp</FormLabel>
                <div className="flex space-x-2">
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <Button
                    type="button"
                    onClick={async () => {
                      setIsDetectingUrlRegexp(true);
                      try {
                        await onDetectUrlRegexp(
                          rootUrl,
                          { parents: parentsConfig, current: currentConfig },
                          path
                        );
                      } finally {
                        setIsDetectingUrlRegexp(false);
                      }
                    }}
                    disabled={!canDetectUrlRegexp}
                  >
                    {isDetectingUrlRegexp ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Detecting...
                      </>
                    ) : (
                      "Detect"
                    )}
                  </Button>
                </div>
                {config.sampleUrls?.length && config.sampleUrls.length > 0 && (
                  <div className="mt-2">
                    <p className="text-sm font-medium">Sample matches:</p>
                    <ul className="text-sm text-muted-foreground mt-1 space-y-1 max-h-32 overflow-y-auto">
                      {config.sampleUrls.map((url, index) => (
                        <li key={index} className="truncate">
                          {url}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={control}
            name={`${path}.pagination`}
            render={({ field }) => (
              <FormItem>
                <div className="flex items-center space-x-2">
                  <FormControl>
                    <Checkbox
                      checked={!!field.value}
                      onCheckedChange={(checked) => {
                        if (checked) {
                          (form.setValue as any)(`${path}.pagination`, {
                            urlPatternType: UrlPatternType.page_num,
                            urlPattern: "",
                            totalPages: 1,
                          });
                        } else {
                          (form.setValue as any)(
                            `${path}.pagination`,
                            undefined
                          );
                        }
                      }}
                    />
                  </FormControl>
                  <FormLabel className="!mt-0">Has Pagination</FormLabel>
                </div>
                {field.value && (
                  <div className="mt-2 space-y-4">
                    <Button
                      type="button"
                      onClick={async () => {
                        setIsDetectingPagination(true);
                        try {
                          await onDetectPagination(
                            rootUrl,
                            {
                              parents: parentsConfig,
                              current: currentConfig,
                            },
                            path
                          );
                        } finally {
                          setIsDetectingPagination(false);
                        }
                      }}
                      disabled={isDetectingPagination}
                    >
                      {isDetectingPagination ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Detecting...
                        </>
                      ) : (
                        "Detect"
                      )}
                    </Button>
                    <div className="space-y-2">
                      <FormField
                        control={control}
                        name={`${path}.pagination.urlPatternType`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Pattern Type</FormLabel>
                            <Select
                              onValueChange={field.onChange}
                              defaultValue={field.value}
                              disabled={isDetectingPagination}
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select a pattern type" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {Object.values(UrlPatternType).map((type) => (
                                  <SelectItem key={type} value={type}>
                                    {type}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={control}
                        name={`${path}.pagination.urlPattern`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>URL Pattern</FormLabel>
                            <FormControl>
                              <Input
                                {...field}
                                disabled={isDetectingPagination}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={control}
                        name={`${path}.pagination.totalPages`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Total Pages</FormLabel>
                            <FormControl>
                              <Input
                                type="number"
                                {...field}
                                disabled={isDetectingPagination}
                                onChange={(e) =>
                                  field.onChange(parseInt(e.target.value))
                                }
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </div>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
        </>
      )}

      <div className="flex space-x-2">
        {config?.pageType !== PageType.DETAIL && (
          <Button
            type="button"
            onClick={() =>
              (form.setValue as any)(`${path}.links`, {
                pageType: PageType.DETAIL,
              })
            }
          >
            Add Level
          </Button>
        )}
        <Button
          type="button"
          variant="destructive"
          onClick={() => (form.setValue as any)(path, undefined)}
        >
          Remove Level
        </Button>
      </div>

      {config?.links && (
        <RecipeLevel
          path={`${path}.links`}
          control={control}
          onDetectUrlRegexp={onDetectUrlRegexp}
          onDetectPagination={onDetectPagination}
        />
      )}
    </div>
  );
}

export default function CreateRecipe() {
  let { catalogueId } = useParams();
  const catalogueQuery = trpc.catalogues.detail.useQuery(
    { id: parseInt(catalogueId || "") },
    { enabled: !!parseInt(catalogueId || "") }
  );
  const createRecipe = trpc.recipes.create.useMutation();
  const detectPagination = trpc.recipes.detectPagination.useMutation();
  const detectUrlRegexp = trpc.recipes.detectUrlRegexp.useMutation();
  const form = useForm<z.infer<typeof FormSchema>>({
    resolver: zodResolver(FormSchema),
    defaultValues: {
      url: "",
      manualConfig: false,
    },
  });
  const { toast } = useToast();
  const [_location, navigate] = useLocation();

  useEffect(() => {
    if (!catalogueQuery.data) {
      return;
    }
    form.reset({ url: catalogueQuery.data.url });
  }, [catalogueQuery.data]);

  useEffect(() => {
    if (form.getValues("manualConfig")) {
      form.setValue("configuration", {
        pageType: PageType.DETAIL,
      });
    } else {
      form.setValue("configuration", undefined);
    }
  }, [form.getValues("manualConfig")]);

  useEffect(() => {
    if (!form.getValues("configuration")) {
      form.setValue("manualConfig", false);
    }
  }, [form.getValues("configuration")]);

  if (!catalogueQuery.data) {
    return null;
  }

  async function onSubmit(data: z.infer<typeof FormSchema>) {
    try {
      const result = await createRecipe.mutateAsync({
        catalogueId: parseInt(catalogueId!),
        url: data.url,
        configuration: data.manualConfig ? data.configuration : undefined,
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
      });
    }
  }

  const breadCrumbs = [
    { label: "Catalogues", href: "/" },
    { label: catalogueQuery.data.name, href: `/${catalogueId}` },
  ];

  const manualConfig = form.watch("manualConfig");
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
                      name="manualConfig"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-start space-x-3 space-y-0">
                          <FormControl>
                            <Checkbox
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                          <div className="space-y-1 leading-none">
                            <FormLabel>Manual configuration</FormLabel>
                            <FormDescription>
                              Manually configure the recipe instead of
                              auto-detection
                            </FormDescription>
                          </div>
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>
              </div>
            </div>

            {manualConfig && (
              <div className="grid gap-2 md:grid-cols-[1fr_250px] lg:grid-cols-2 lg:gap-4">
                <Card>
                  <CardHeader>
                    <CardDescription>Recipe Configuration</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {configuration && (
                      <RecipeLevel
                        path="configuration"
                        control={form.control}
                        onDetectUrlRegexp={onDetectUrlRegexp}
                        onDetectPagination={onDetectPagination}
                      />
                    )}
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
