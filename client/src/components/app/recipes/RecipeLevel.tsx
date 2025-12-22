import { useFormContext, Path } from "react-hook-form";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { HelpCircle, Loader2 } from "lucide-react";
import { PageType, PaginationConfiguration, UrlPatternType } from "../../../../../common/types";

export type FormRecipeConfiguration = {
  pageType: PageType;
  linkRegexp?: string;
  pagination?: PaginationConfiguration;
  links?: FormRecipeConfiguration;
  clickSelector?: string;
  clickOptions?: { limit?: number; waitMs?: number };
  sampleUrls?: string[];
  pageLoadWaitTime?: number;
  exactLinkPatternMatch?: boolean;
};

interface RecipeLevelProps {
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
}

export function RecipeLevel({
  path,
  control,
  onDetectUrlRegexp,
  onDetectPagination,
}: RecipeLevelProps) {
  const form = useFormContext();
  const config = form.watch(path as any) as FormRecipeConfiguration;
  const [isDetectingUrlRegexp, setIsDetectingUrlRegexp] = useState(false);
  const [isDetectingPagination, setIsDetectingPagination] = useState(false);
  const [tooltipOpen, setTooltipOpen] = useState<{ [key: string]: boolean }>({});

  const rootUrl = form.watch("url");

  const currentConfig = form.getValues(path as any) as FormRecipeConfiguration;
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
    <TooltipProvider>
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
                  ) as FormRecipeConfiguration;
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
                  field.onChange(value);
                }}
                value={field.value}
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
            <FormItem className="flex flex-row items-start space-x-3 space-y-0">
              <FormControl>
                <Checkbox
                  checked={config?.clickSelector !== undefined}
                  onCheckedChange={(checked) => {
                    if (checked) {
                      // When checked, initialize clickSelector with "body" and set default limit
                      form.setValue(
                        `${path}.clickSelector` as Path<any>,
                        "body",
                        { shouldValidate: false }
                      );
                      const clickOptionsPath =
                        `${path}.clickOptions` as Path<any>;
                      const currentClickOptions =
                        form.getValues(clickOptionsPath);
                      if (!currentClickOptions?.limit) {
                        form.setValue(
                          clickOptionsPath as Path<any>,
                          { limit: 300 },
                          { shouldValidate: false }
                        );
                      }
                    } else {
                      // When unchecked, clear clickSelector and clickOptions
                      form.setValue(
                        `${path}.clickSelector` as Path<any>,
                        undefined,
                        { shouldValidate: false }
                      );
                      form.setValue(
                        `${path}.clickOptions` as Path<any>,
                        undefined,
                        { shouldValidate: false }
                      );
                    }
                  }}
                />
              </FormControl>
              <div className="space-y-1 leading-none">
                <FormLabel>Dynamic catalogue</FormLabel>
                <FormDescription>
                  Enable dynamic link discovery by simulating clicks on the
                  elements on the page. This is needed for catalogues that do
                  not use classic page navigation and are more dynamic in
                  nature.
                </FormDescription>
              </div>
            </FormItem>

            {config?.clickSelector !== undefined && (
              <>
                <FormField
                  control={control}
                  name={`${path}.clickSelector`}
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="flex items-center gap-2">
                        Dynamic URL Selector
                        <span className="text-destructive">*</span>
                        <Tooltip
                          open={tooltipOpen[`${path}-selector`] || false}
                          onOpenChange={(open) =>
                            setTooltipOpen((prev) => ({
                              ...prev,
                              [`${path}-selector`]: open,
                            }))
                          }
                        >
                          <TooltipTrigger asChild>
                            <HelpCircle
                              className="h-4 w-4 text-muted-foreground cursor-help"
                              onClick={(e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                setTooltipOpen((prev) => ({
                                  ...prev,
                                  [`${path}-selector`]:
                                    !prev[`${path}-selector`],
                                }));
                              }}
                            />
                          </TooltipTrigger>
                          <TooltipContent className="max-w-xs">
                            <p>
                              This is the selector of the element that contains
                              the things xTRA will try to click on. You can find
                              this by using the developer tools on the catalogue
                              webpage. "body" by default should encompass all
                              clickable elements, but it is highly recommended
                              to set a more specific element to avoid proxy
                              costs or stopping because of max clicks allowed.
                              Note that using this method, pages will take
                              longer to index and the regex tester can take up
                              to 5 minutes to show results.
                            </p>
                          </TooltipContent>
                        </Tooltip>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="e.g. a.nav-link" {...field} />
                      </FormControl>
                      <FormDescription>
                        Required when Dynamic catalogue is enabled. The selector
                        of elements to click.
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={control}
                    name={`${path}.clickOptions.limit`}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="flex items-center gap-2">
                          Click Limit
                          <Tooltip
                            open={tooltipOpen[`${path}-limit`] || false}
                            onOpenChange={(open) =>
                              setTooltipOpen((prev) => ({
                                ...prev,
                                [`${path}-limit`]: open,
                              }))
                            }
                          >
                            <TooltipTrigger asChild>
                              <HelpCircle
                                className="h-4 w-4 text-muted-foreground cursor-help"
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  setTooltipOpen((prev) => ({
                                    ...prev,
                                    [`${path}-limit`]: !prev[`${path}-limit`],
                                  }));
                                }}
                              />
                            </TooltipTrigger>
                            <TooltipContent className="max-w-xs">
                              <p>
                                This is a safety limit against infinite loops.
                                Adjust this value if you expect the page to have
                                more than 300 clickable elements.
                              </p>
                            </TooltipContent>
                          </Tooltip>
                        </FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            value={
                              field.value ?? (config.clickSelector ? 300 : "")
                            }
                            onChange={(e) =>
                              field.onChange(
                                e.target.value === ""
                                  ? undefined
                                  : parseInt(e.target.value)
                              )
                            }
                          />
                        </FormControl>
                        <FormDescription>
                          Maximum number of elements to click (optional).
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={control}
                    name={`${path}.clickOptions.waitMs`}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Wait after click (ms)</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            value={field.value ?? ""}
                            onChange={(e) =>
                              field.onChange(
                                e.target.value === ""
                                  ? undefined
                                  : parseInt(e.target.value)
                              )
                            }
                          />
                        </FormControl>
                        <FormDescription>
                          Optional delay after each click.
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </>
            )}

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
                  {config.sampleUrls?.length &&
                    config.sampleUrls.length > 0 && (
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
              name={`${path}.exactLinkPatternMatch`}
              render={({ field }) => (
                <FormItem className="flex flex-row items-start space-x-2 space-y-0">
                  <FormControl>
                    <Checkbox
                      checked={field.value ?? config?.exactLinkPatternMatch ?? false}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                  <div className="leading-none">
                    <FormLabel className="flex items-center gap-1 space-x-0 space-y-0">
                      Use exact Regex match in URL subpages.
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <HelpCircle className="h-4 w-4 text-muted-foreground cursor-help" />
                        </TooltipTrigger>
                        <TooltipContent className="max-w-[550px] break-words">
                          <p className="mb-2">
                            This controls how xTRA uses links in a page to
                            enqueue sub-pages for crawling & extraction.

                            When enabled, xTRA will only use 
                            the sub-segment that exactly matches the link
                            pattern. So for example, if the link pattern is
                            <span className="font-mono mx-1">course\/([A-Za-z0-9]+)</span> and the URL is 
                            <span className="font-mono mx-1">/2025-2026/course/acb</span> then the page enqueued will be 
                            <span className="font-mono mx-1">/course/acb</span> instead of <span className="font-mono mx-1">/2025-2026/course/acb</span> which
                            is the default behavior without this flag.
                          </p>
                          <p className="mb-2">
                            This is needed when catalogues use links that are
                            not correctly resolved in relation to their parent page.
                            For example, The Antelope Valley College uses links such
                            as <span className="font-mono">/2025-2026/course/acb</span> in its courses index page
                            but the catalogue index page already contains the 
                            <span className="font-mono">2025-2026</span> segment leading to URLs being
                            formed to <span className="font-mono">/2025-2026/2025-2026/course/acb</span> instead of 
                            <span className="font-mono">/2025-2026/course/acb</span>.
                            Browsers handle this correctly but
                            NodeJS URL built-in helper keeps the <span className="font-mono">2025-2026</span> duplicate segment.
                          </p>
                          <p>
                            <b>Recommended to keep it disabled unless absolutely necessary.</b>
                          </p>
                        </TooltipContent>
                      </Tooltip>
                    </FormLabel>
                  </div>
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
                                value={field.value}
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
    </TooltipProvider>
  );
}

