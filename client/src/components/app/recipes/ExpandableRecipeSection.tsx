import { cn } from "@/utils";
import type { ReactNode } from "react";

export type ExpandableRecipeSectionProps = {
  /** When true, `children` are shown below the header row. */
  expanded: boolean;
  /** Checkbox control (typically wrapped in `FormControl`). Omit for static sections. */
  checkbox?: ReactNode;
  /** Label beside the checkbox, or a section title when there is no checkbox. */
  label?: ReactNode;
  /** Body below the header; only mounted when `expanded` is true. */
  children?: ReactNode;
  className?: string;
  /** Classes for the body region (e.g. `space-y-3 pl-6`). */
  contentClassName?: string;
};

/**
 * Card-style layout for recipe configuration: optional checkbox + label row,
 * then fields. For always-on groups, omit `checkbox`, set `expanded` to true,
 * and optionally omit `label` to only wrap `children` in the card.
 */
export function ExpandableRecipeSection({
  expanded,
  checkbox,
  label,
  children,
  className,
  contentClassName,
}: ExpandableRecipeSectionProps) {
  const hasHeader = checkbox != null || label != null;

  return (
    <div
      className={cn(
        "space-y-4 rounded-lg border bg-background p-4 transition-colors hover:bg-muted/50",
        className
      )}
    >
      {hasHeader && (
        <div className="flex flex-row items-start space-x-3 space-y-0">
          {checkbox}
          {label != null && (
            <div className="min-w-0 flex-1 space-y-1 leading-none">{label}</div>
          )}
        </div>
      )}
      {expanded && children != null && (
        <div className={cn(contentClassName)}>{children}</div>
      )}
    </div>
  );
}
