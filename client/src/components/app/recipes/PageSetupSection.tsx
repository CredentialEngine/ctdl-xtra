import {
  Control,
  UseFormSetValue,
  useFieldArray,
  useWatch,
} from "react-hook-form";
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ChevronDown, ChevronUp, HelpCircle, Trash2 } from "lucide-react";
import { PageSetupStep } from "../../../../../common/types";
import { ExpandableRecipeSection } from "./ExpandableRecipeSection";

interface PageSetupSectionProps {
  basePath: string;
  control: Control<any>;
  setValue: UseFormSetValue<any>;
}

export function PageSetupSection({
  basePath,
  control,
  setValue,
}: PageSetupSectionProps) {
  const pageSetupPath = `${basePath}.pageSetup` as const;
  const stepsFieldName = `${basePath}.pageSetup.steps` as const;

  const pageSetup = useWatch({ control, name: pageSetupPath });

  const { fields, append, remove, move } = useFieldArray({
    control,
    name: stepsFieldName,
  });

  const setPageSetup = (next: { enabled: boolean; steps: PageSetupStep[] }) => {
    setValue(pageSetupPath, next, { shouldDirty: true });
  };

  return (
    <FormField
      control={control}
      name={`${basePath}.pageSetup.enabled`}
      render={({ field }) => (
        <FormItem className="space-y-0">
          <ExpandableRecipeSection
            expanded={field.value ?? false}
            checkbox={
              <FormControl>
                <Checkbox
                  checked={field.value ?? false}
                  onBlur={field.onBlur}
                  ref={field.ref}
                  name={field.name}
                  onCheckedChange={(checked) => {
                    const next = checked === true;
                    setPageSetup({
                      enabled: next,
                      steps: pageSetup?.steps ?? [],
                    });
                  }}
                />
              </FormControl>
            }
            label={
              <FormLabel className="flex items-center gap-1.5">
                Page actions
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className="inline-flex shrink-0 rounded-full text-muted-foreground outline-offset-2 hover:text-foreground focus-visible:outline focus-visible:ring-2 focus-visible:ring-ring"
                      aria-label="What are page actions?"
                    >
                      <HelpCircle className="h-4 w-4 cursor-help" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-sm text-left" side="top">
                    <p>
                      Page actions can be defined to set the page in a specific
                      state before xTRA performs its actions on the page,
                      depending on page type. This is useful for certain
                      catalogues that have a dynamic nature. For example,
                      catalogues that display course content but do not use
                      regular page links choosing to use user events instead
                      such as clicks or scrolls.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </FormLabel>
            }
            contentClassName="space-y-3 pl-6"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm text-muted-foreground">Add step:</span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => append({ type: "click", selector: "" })}
              >
                Click
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => append({ type: "wait", seconds: 1 })}
              >
                Wait
              </Button>
            </div>

            {fields.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No steps yet. Add a click or wait step above.
              </p>
            ) : (
              <ul className="space-y-3">
                {fields.map((fieldItem, index) => {
                  const row = fieldItem as PageSetupStep & { id: string };
                  const step: PageSetupStep =
                    pageSetup?.steps?.[index] ?? {
                      type: row.type,
                      ...(row.type === "click"
                        ? { selector: row.selector }
                        : { seconds: row.seconds }),
                    };
                  return (
                    <li
                      key={fieldItem.id}
                      className="flex flex-col gap-2 rounded-md border bg-muted/30 p-3 sm:flex-row sm:items-start"
                    >
                      <div className="min-w-0 flex-1 space-y-2">
                        {step.type === "click" && (
                          <FormField
                            control={control}
                            name={`${basePath}.pageSetup.steps.${index}.selector`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormLabel className="text-xs">
                                  Step {index + 1} — Element selector
                                </FormLabel>
                                <FormControl>
                                  <Input
                                    placeholder="CSS selector"
                                    {...f}
                                    value={f.value ?? ""}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        )}
                        {step.type === "wait" && (
                          <FormField
                            control={control}
                            name={`${basePath}.pageSetup.steps.${index}.seconds`}
                            render={({ field: f }) => (
                              <FormItem>
                                <FormLabel className="text-xs">
                                  Step {index + 1} — Wait (seconds)
                                </FormLabel>
                                <FormControl>
                                  <Input
                                    type="number"
                                    min={1}
                                    max={600}
                                    {...f}
                                    onChange={(e) => {
                                      const v = e.target.value
                                        ? parseFloat(e.target.value)
                                        : 1;
                                      f.onChange(Number.isFinite(v) ? v : 1);
                                    }}
                                    value={f.value ?? ""}
                                  />
                                </FormControl>
                                <FormMessage />
                              </FormItem>
                            )}
                          />
                        )}
                      </div>
                      <div className="flex shrink-0 gap-1 self-end sm:self-start">
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          disabled={index === 0}
                          onClick={() => move(index, index - 1)}
                          aria-label="Move step up"
                        >
                          <ChevronUp className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-8 w-8"
                          disabled={index >= fields.length - 1}
                          onClick={() => move(index, index + 1)}
                          aria-label="Move step down"
                        >
                          <ChevronDown className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="h-8 w-8 text-destructive"
                          onClick={() => remove(index)}
                          aria-label="Remove step"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </ExpandableRecipeSection>
        </FormItem>
      )}
    />
  );
}
