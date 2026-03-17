import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { UIPageStatus } from "@common/types";
import { concisePrintDate, resolveCrawlPageUrl, trpc } from "@/utils";
import { ExtractionStatus, PageStatus } from "@/utils";
import {
  ChevronsUpDown,
  ExternalLink as ExternalLinkIcon,
  FileJson,
  FileText as FileTextIcon,
  HelpCircle,
  ScrollText as ScrollTextIcon,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

interface MultiSelectOption<T> {
  value: T;
  label: string;
}

interface MultiSelectProps<T> {
  label?: string;
  options: MultiSelectOption<T>[];
  value: T[];
  onChange: (value: T[]) => void;
  searchPlaceholder?: string;
  emptyMessage?: string;
}

function MultiSelect<T extends string>({
  label,
  options,
  value,
  onChange,
  searchPlaceholder = "Search...",
  emptyMessage = "No results found.",
}: MultiSelectProps<T>) {
  const [open, setOpen] = useState(false);

  const triggerLabel =
    value.length === 0
      ? "None"
      : value.length === options.length
        ? "All"
        : value
            .map((v) => options.find((o) => o.value === v)?.label ?? v)
            .join(", ");

  const toggle = (itemValue: T) => {
    onChange(
      value.includes(itemValue)
        ? value.filter((v) => v !== itemValue)
        : [...value, itemValue]
    );
  };

  const selectAll = () => onChange(options.map((o) => o.value));
  const selectNone = () => onChange([]);

  return (
    <div>
      {label && (
        <label className="text-sm font-medium mb-1 block">{label}</label>
      )}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between font-normal"
          >
            <span className="truncate">{triggerLabel}</span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[200px] p-0" align="start">
          <Command>
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              <CommandEmpty>{emptyMessage}</CommandEmpty>
              <CommandGroup>
                <CommandItem
                  value="all"
                  onSelect={selectAll}
                  className="justify-center font-medium"
                >
                  All
                </CommandItem>
                <CommandItem
                  value="none"
                  onSelect={selectNone}
                  className="justify-center font-medium"
                >
                  None
                </CommandItem>
                {options.map((opt) => (
                  <CommandItem
                    key={opt.value}
                    value={opt.label}
                    onSelect={() => toggle(opt.value)}
                  >
                    <Checkbox
                      checked={value.includes(opt.value)}
                      className="mr-2"
                    />
                    {opt.label}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}

const DATA_STATUS_OPTIONS: { value: "present" | "absent"; label: string }[] = [
  { value: "present", label: "Present" },
  { value: "absent", label: "Absent" },
];

const SORT_OPTIONS = [
  { value: "random", label: "Random" },
  { value: "most_expensive", label: "Most expensive" },
  { value: "most_data_items", label: "Most data items" },
  { value: "least_data_items", label: "Least data items" },
];

const STATUS_HELP: Record<string, string> = {
  [PageStatus.WAITING]:
    "Queued — The page hasn't been processed yet; it's waiting its turn.",
  [PageStatus.IN_PROGRESS]:
    "In progress — The system is currently working on this page.",
  [PageStatus.DOWNLOADED]:
    "Downloaded — The page content was successfully retrieved from the website and is awaiting extraction.",
  [PageStatus.SUCCESS]:
    "Success — Useful information was successfully pulled from this page.",
  [PageStatus.EXTRACTED_NO_DATA]:
    "No data found — either the data is not present in the page, the model couldn't find the expected information or the page was not correctly converted to the simplified content form.",
  [PageStatus.ERROR]:
    "Error — Something went wrong (e.g. the page couldn't load or timed out).",
};

type SampledPage = {
  id: number;
  extractionId: number;
  crawlStepId: number;
  url: string;
  status: string;
  pageType: string | null;
  createdAt: string;
  dataItemCount: number;
  tokenSum: number;
};

function formatThousands(n: number): string {
  if (n === 0) return "0";
  const k = n / 1_000;
  return k % 1 === 0 ? `${k}K` : `${k.toFixed(1)}K`;
}

interface SampleModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  extractionId: number;
  extractionStatus?: string;
  /** Catalogue base URL for resolving relative crawl page URLs */
  recipeUrl?: string;
}

export default function SampleModal({
  open,
  onOpenChange,
  extractionId,
  extractionStatus,
  recipeUrl,
}: SampleModalProps) {
  const isExtractionInProgress = [
    ExtractionStatus.IN_PROGRESS,
    ExtractionStatus.WAITING,
  ].includes(extractionStatus as ExtractionStatus);
  const [sampleSizePercent, setSampleSizePercent] = useState(5);
  const [dataStatus, setDataStatus] = useState<("present" | "absent")[]>([
    "present",
  ]);
  const [statuses, setStatuses] = useState<PageStatus[]>(() =>
    UIPageStatus.map((o) => o.value)
  );
  const [sortBy, setSortBy] = useState<
    "random" | "most_expensive" | "most_data_items" | "least_data_items"
  >("random");

  const [appliedFilters, setAppliedFilters] = useState<{
    sampleSizePercent: number;
    dataStatus: ("present" | "absent")[];
    statuses: PageStatus[];
    sortBy: "random" | "most_expensive" | "most_data_items" | "least_data_items";
    applyKey: number;
  } | null>(null);

  useEffect(() => {
    if (!open) {
      setAppliedFilters(null);
    }
  }, [open]);

  const filtersDirty = useMemo(() => {
    if (!appliedFilters) return false;
    const arrEq = (a: string[], b: string[]) =>
      a.length === b.length && a.every((v, i) => v === b[i]);
    return (
      appliedFilters.sampleSizePercent !== sampleSizePercent ||
      !arrEq([...appliedFilters.dataStatus].sort(), [...dataStatus].sort()) ||
      !arrEq([...appliedFilters.statuses].sort(), [...statuses].sort()) ||
      appliedFilters.sortBy !== sortBy
    );
  }, [appliedFilters, sampleSizePercent, dataStatus, statuses, sortBy]);

  const sampleQuery = trpc.extractions.samplePages.useQuery(
    {
      extractionId,
      sampleSizePercent: appliedFilters?.sampleSizePercent ?? 5,
      dataStatus: appliedFilters?.dataStatus ?? ["present"],
      statuses: appliedFilters?.statuses ?? [],
      sortBy: appliedFilters?.sortBy ?? "random",
      applyKey: appliedFilters?.applyKey ?? 0,
    },
    {
      enabled: appliedFilters !== null && open,
    }
  );

  const sampledPages = (sampleQuery.data ?? []) as SampledPage[];

  const onApplyFilter = useCallback(() => {
    setAppliedFilters((prev) => ({
      sampleSizePercent,
      dataStatus: [...dataStatus],
      statuses: [...statuses],
      sortBy,
      applyKey: (prev?.applyKey ?? 0) + 1,
    }));
  }, [sampleSizePercent, dataStatus, statuses, sortBy]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-[66vw] w-[66vw] max-h-[66vh] h-[66vh] flex flex-col p-0 gap-0"
        onPointerDownOutside={(e) => e.preventDefault()}
      >
        <DialogHeader className="px-6 pt-6 pb-4 shrink-0">
          <DialogTitle>Sample extraction items</DialogTitle>
          {appliedFilters && !sampleQuery.isLoading && (
            <p className="text-sm text-muted-foreground mt-1">
              {sampledPages.length} item{sampledPages.length !== 1 ? "s" : ""}
            </p>
          )}
        </DialogHeader>

        {isExtractionInProgress && (
          <div className="mx-6 mb-4 px-4 py-3 rounded-md bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-200 text-sm shrink-0">
            Extraction is in progress. Data will change.
          </div>
        )}

        <div className="flex flex-col flex-1 min-h-0 px-6 pb-6">
          {/* Filter section */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4 shrink-0">
            <div>
              <label className="text-sm font-medium mb-1 block">
                Sample size (%)
              </label>
              <Input
                type="number"
                min={0}
                max={100}
                value={sampleSizePercent}
                onChange={(e) =>
                  setSampleSizePercent(
                    Math.min(100, Math.max(0, parseInt(e.target.value) || 0))
                  )
                }
              />
            </div>
            <MultiSelect
              label="Data status"
              options={DATA_STATUS_OPTIONS}
              value={dataStatus}
              onChange={setDataStatus}
              searchPlaceholder="Search..."
              emptyMessage="No option found."
            />
            <div>
              <label className="text-sm font-medium mb-1 block">
                <span className="inline-flex items-center gap-1">
                  Status
                  <TooltipProvider>
                    <Tooltip delayDuration={200}>
                      <TooltipTrigger asChild>
                        <HelpCircle className="h-3.5 w-3.5 text-muted-foreground cursor-help shrink-0" />
                      </TooltipTrigger>
                      <TooltipContent
                        side="top"
                        align="start"
                        className="max-w-[280px] space-y-1.5 p-3"
                      >
                        {UIPageStatus.map(({ value, label }) => (
                          <p key={value} className="text-xs leading-snug">
                            <span className="font-medium">{label}:</span>{" "}
                            {STATUS_HELP[value]}
                          </p>
                        ))}
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </span>
              </label>
              <MultiSelect
                options={UIPageStatus}
                value={statuses}
                onChange={setStatuses}
                searchPlaceholder="Search status..."
                emptyMessage="No status found."
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Sort by</label>
              <Select
                value={sortBy}
                onValueChange={(
                  v:
                    | "random"
                    | "most_expensive"
                    | "most_data_items"
                    | "least_data_items"
                ) => setSortBy(v)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SORT_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end col-span-2 md:col-span-1">
              <Button
                onClick={onApplyFilter}
                disabled={sampleQuery.isFetching}
              >
                {sampleQuery.isFetching ? "Applying..." : "Apply filter"}
              </Button>
            </div>
          </div>

          {filtersDirty && (
            <div className="mb-4 px-4 py-3 rounded-md bg-muted border text-muted-foreground text-sm shrink-0">
              Filters have changed. Click Apply filter to update results.
            </div>
          )}

          {/* Table section */}
          <div className="flex-1 min-h-0 border rounded-md overflow-hidden">
            {!appliedFilters ? (
              <div className="h-full flex items-center justify-center text-muted-foreground">
                Click Apply Filter
              </div>
            ) : sampleQuery.isLoading ? (
              <div className="h-full flex items-center justify-center text-muted-foreground">
                Loading...
              </div>
            ) : sampledPages.length === 0 ? (
              <div className="h-full flex items-center justify-center text-muted-foreground">
                No pages match the filter
              </div>
            ) : (
              <div className="h-full overflow-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="text-xs">
                      <TableHead>ID</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Created</TableHead>
                      <TableHead className="max-w-[200px]">URL</TableHead>
                      <TableHead className="text-right">Data items</TableHead>
                      <TableHead className="text-right">Tokens used</TableHead>
                      <TableHead className="text-right w-[140px]">
                        Actions
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody className="text-xs">
                    {sampledPages.map((page) => (
                      <TableRow key={page.id}>
                        <TableCell>{page.id}</TableCell>
                        <TableCell>{page.status}</TableCell>
                        <TableCell>{concisePrintDate(page.createdAt)}</TableCell>
                        <TableCell className="max-w-[200px] truncate" title={page.url}>
                          {page.url}
                        </TableCell>
                        <TableCell className="text-right">
                          {page.dataItemCount ?? 0}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatThousands(page.tokenSum)}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex gap-1 justify-end">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              title="Open catalogue URL in new tab"
                              onClick={() =>
                                window.open(
                                  recipeUrl
                                    ? resolveCrawlPageUrl(page.url, recipeUrl)
                                    : page.url,
                                  "_blank",
                                  "noopener,noreferrer"
                                )
                              }
                            >
                              <ExternalLinkIcon className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              title="Show extracted data"
                              asChild
                            >
                              <a
                                href={`/extractions/${extractionId}/steps/${page.crawlStepId}/items/${page.id}?tabName=data`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <FileJson className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              title="Show simplified content"
                              asChild
                            >
                              <a
                                href={`/extractions/${extractionId}/steps/${page.crawlStepId}/items/${page.id}?tabName=simplified_content`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <FileTextIcon className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7"
                              title="Show operation logs"
                              asChild
                            >
                              <a
                                href={`/extractions/${extractionId}/steps/${page.crawlStepId}/items/${page.id}?tabName=operation_logs`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                <ScrollTextIcon className="h-3.5 w-3.5" />
                              </a>
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
