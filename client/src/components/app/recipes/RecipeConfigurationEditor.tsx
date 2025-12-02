import { Control, UseFormSetValue } from "react-hook-form";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/use-toast";
import { CatalogueType } from "../../../../../common/types";
import { trpc } from "@/utils";
import { RecipeLevel, FormRecipeConfiguration } from "./RecipeLevel";

type RecipeFormData = {
  url: string;
  configuration?: FormRecipeConfiguration;
  isTemplate?: boolean;
};

interface RecipeConfigurationEditorProps {
  control: Control<RecipeFormData>;
  setValue: UseFormSetValue<RecipeFormData>;
  rootUrl: string;
  catalogueType: CatalogueType;
}

export function RecipeConfigurationEditor({
  control,
  setValue,
  catalogueType,
}: RecipeConfigurationEditorProps) {
  const { toast } = useToast();
  const detectPagination = trpc.recipes.detectPagination.useMutation();
  const detectUrlRegexp = trpc.recipes.detectUrlRegexp.useMutation();

  async function onDetectPagination(
    rootUrl: string,
    context: {
      parents?: FormRecipeConfiguration[];
      current: FormRecipeConfiguration;
    },
    formPath?: string
  ) {
    try {
      const url = context.parents
        ? context.parents[context.parents.length - 1]?.sampleUrls![0]
        : rootUrl;
      const result = await detectPagination.mutateAsync({
        url,
        catalogueType,
      });
      if (result) {
        const paginationPath = formPath
          ? `${formPath}.pagination`
          : "configuration.pagination";
        setValue(`${paginationPath}.urlPatternType` as any, result.urlPatternType);
        setValue(`${paginationPath}.urlPattern` as any, result.urlPattern);
        setValue(`${paginationPath}.totalPages` as any, result.totalPages);
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
    try {
      const urls = context.parents
        ? context.parents[context.parents.length - 1]?.sampleUrls!.slice(0, 2)
        : [rootUrl];
      const result = await detectUrlRegexp.mutateAsync({
        urls,
        pageType: context.current.pageType,
        catalogueType,
      });
      if (result) {
        if (formPath) {
          setValue(`${formPath}.linkRegexp` as any, result.regexp);
        } else {
          setValue("configuration.linkRegexp" as any, result.regexp);
        }

        if (result.urls) {
          if (formPath) {
            setValue(
              `${formPath}.sampleUrls` as any,
              result.urls.slice(0, 10)
            );
          } else {
            setValue(
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
    <div className="space-y-4">
      <FormField
        control={control}
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
                value={(field.value ?? "") as string | number}
              />
            </FormControl>
            <FormDescription>
              How long to wait (in seconds) for the page to fully load after opening. This is useful for pages that dynamically load content. Leave empty or 0 for no additional wait.
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />
      <RecipeLevel
        path="configuration"
        control={control}
        onDetectUrlRegexp={onDetectUrlRegexp}
        onDetectPagination={onDetectPagination}
      />
    </div>
  );
}

