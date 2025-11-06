import { useFormContext } from "react-hook-form";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  FormControl,
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
import { Loader2 } from "lucide-react";
import { PageType, PaginationConfiguration, UrlPatternType } from "../../../../../common/types";

export type FormRecipeConfiguration = {
  pageType: PageType;
  linkRegexp?: string;
  pagination?: PaginationConfiguration;
  links?: FormRecipeConfiguration;
  sampleUrls?: string[];
  pageLoadWaitTime?: number;
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
  );
}

