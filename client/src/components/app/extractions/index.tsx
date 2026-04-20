import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCallback, useEffect, useMemo, useState } from "react";
import { IterableElement, prettyPrintDate, RouterOutput, trpc } from "@/utils";
import { API_URL } from "@/constants";
import { Download, Earth, Pickaxe } from "lucide-react";
import { Link, useLocation } from "wouter";

import { Card, CardContent, CardFooter } from "@/components/ui/card";
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
import usePagination from "../usePagination";

type ExtractionSummary = IterableElement<
  RouterOutput["extractions"]["list"]["results"]
>;

type SortKey =
  | "catalogue"
  | "type"
  | "status"
  | "date"
  | "cost";
type SortOrder = "asc" | "desc";

const VALID_SORT_KEYS: SortKey[] = [
  "catalogue",
  "type",
  "status",
  "date",
  "cost",
];

function toStartOfDayIso(date?: string) {
  return date ? `${date}T00:00:00.000Z` : undefined;
}

function toEndOfDayIso(date?: string) {
  return date ? `${date}T23:59:59.999Z` : undefined;
}

function getBasePath(currentLocation?: string) {
  return currentLocation?.split("?")[0] || "/extractions";
}

function getNextSortOrder(
  currentKey: SortKey,
  clickedKey: SortKey,
  currentOrder: SortOrder
): SortOrder {
  const defaultDesc: SortKey[] = ["date", "cost"];
  return currentKey === clickedKey
    ? currentOrder === "asc"
      ? "desc"
      : "asc"
    : defaultDesc.includes(clickedKey)
      ? "desc"
      : "asc";
}

function parseSearch(search: string): {
  sortKey: SortKey;
  sortOrder: SortOrder;
  dateFrom?: string;
  dateTo?: string;
} {
  const sp = new URLSearchParams(search);
  const key = sp.get("sort");
  const order = sp.get("order");

  const sortKey = VALID_SORT_KEYS.includes((key || "") as SortKey)
    ? (key as SortKey)
    : "date";
  const sortOrder: SortOrder =
    order === "asc" || order === "desc" ? (order as SortOrder) : "desc";

  const dateFrom = sp.get("from") || undefined;
  const dateTo = sp.get("to") || undefined;
  return { sortKey, sortOrder, dateFrom, dateTo };
}

const ExtractionListItem = ({
  extraction,
  onOpen,
}: {
  extraction: ExtractionSummary;
  onOpen: (id: ExtractionSummary["id"]) => void;
}) => {
  const catalogue = extraction.recipe.catalogue;
  let totalDownloads = 0,
    totalDownloadsAttempted = 0,
    totalExtractionsPossible = 0,
    totalExtractionsAttempted = 0,
    totalExtractedItems = 0;
  for (const step of extraction.completionStats?.steps || []) {
    totalDownloads += step.downloads.total;
    totalDownloadsAttempted += step.downloads.attempted;
    totalExtractionsPossible += step.downloads.succeeded;
    totalExtractionsAttempted += step.extractions.attempted;
    totalExtractedItems += step.extractions.courses;
  }
  const downloadsPercent =
    totalDownloads > 0
      ? `${Math.floor((totalDownloadsAttempted / totalDownloads) * 100)}%`
      : "0%";
  const extractionsPercent =
    totalExtractionsPossible > 0
      ? `${Math.floor((totalExtractionsAttempted / totalExtractionsPossible) * 100)}%`
      : "0%";
  return (
    <TableRow
      className="cursor-pointer hover:bg-muted/50"
      onClick={() => onOpen(extraction.id)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(extraction.id);
        }
      }}
      tabIndex={0}
    >
      <TableCell>
        <div className="flex items-center gap-4">
          {catalogue?.thumbnailUrl ? (
            <img src={catalogue.thumbnailUrl} style={{ maxHeight: "30px" }} />
          ) : null}
          {catalogue?.name || "Unknown"}
        </div>
      </TableCell>
      <TableCell className="text-xs">
        {extraction.recipe.name}
      </TableCell>
      <TableCell className="font-medium">
        {catalogue?.catalogueType || "-"}
      </TableCell>
      <TableCell className="text-xs">{extraction.status}</TableCell>
      <TableCell className="text-xs">
        {extraction.completionStats ? (
          <TooltipProvider>
            <div className="flex items-center gap-1">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Download className="h-3.5 w-3.5 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent>Downloads</TooltipContent>
              </Tooltip>
              <span className="inline-block w-8">{downloadsPercent}</span>
              <span>/</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Pickaxe className="h-3.5 w-3.5 text-muted-foreground" />
                </TooltipTrigger>
                <TooltipContent>Extractions</TooltipContent>
              </Tooltip>
              <span className="inline-block w-8">{extractionsPercent}</span>
            </div>
          </TooltipProvider>
        ) : (
          "Pending"
        )}
      </TableCell>
      <TableCell className="text-xs">
        {extraction.completionStats?.costs?.estimatedCost != null
          ? `$${extraction.completionStats.costs.estimatedCost.toFixed(2)}`
          : "-"}
      </TableCell>
      <TableCell className="text-xs">
        {totalExtractedItems.toLocaleString()}
      </TableCell>
      <TableCell className="text-xs">
        {prettyPrintDate(extraction.createdAt)}
      </TableCell>
    </TableRow>
  );
};

export default function Extractions() {
  const { page, PaginationButtons } = usePagination();
  const [location, navigate] = useLocation();
  const [exportInProgress, setExportInProgress] = useState(false);
  const [{ sortKey, sortOrder, dateFrom, dateTo }, setQuery] = useState(() =>
    parseSearch(window.location.search)
  );

  useEffect(() => {
    setQuery(parseSearch(window.location.search));
  }, [location]);
  const dateFromIso = useMemo(() => toStartOfDayIso(dateFrom), [dateFrom]);
  const dateToIso = useMemo(() => toEndOfDayIso(dateTo), [dateTo]);
  const listQuery = trpc.extractions.list.useQuery({
    page,
    sortKey,
    sortOrder,
    dateFrom: dateFromIso,
    dateTo: dateToIso,
  });

  const handleSort = useCallback(
    (key: SortKey) => {
      const nextKey = key;
      const nextOrder: SortOrder = getNextSortOrder(sortKey, key, sortOrder);
      setQuery((prev) => ({ ...prev, sortKey: nextKey, sortOrder: nextOrder }));
      const sp = new URLSearchParams(window.location.search);
      sp.set("sort", nextKey);
      sp.set("order", nextOrder);
      const basePath = getBasePath(location);
      navigate(`${basePath}?${sp.toString()}`);
    },
    [sortKey, sortOrder, navigate, location]
  );

  const handleDateChange = useCallback(
    (which: "from" | "to", value: string) => {
      // Update local state immediately so inputs reflect the selected dates
      setQuery((prev) =>
        which === "from"
          ? { ...prev, dateFrom: value || undefined }
          : { ...prev, dateTo: value || undefined }
      );
      const sp = new URLSearchParams(window.location.search);
      if (value) {
        sp.set(which === "from" ? "from" : "to", value);
      } else {
        sp.delete(which === "from" ? "from" : "to");
      }
      const basePath = getBasePath(location);
      navigate(`${basePath}?${sp.toString()}`);
    },
    [navigate, location]
  );

  const handleExport = useCallback(() => {
    setExportInProgress(true);
    const params = new URLSearchParams();
    if (dateFrom) params.set("from", dateFrom);
    if (dateTo) params.set("to", dateTo);
    const filename = `extractions_${dateFrom || "all"}_${dateTo || "all"}.csv`;
    fetch(`${API_URL}/downloads/extractions_csv?${params.toString()}`, {
      credentials: "include",
    })
      .then((response) => response.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch((err) => console.error("Export error:", err))
      .finally(() => setExportInProgress(false));
  }, [dateFrom, dateTo]);

  const renderHeader = (label: string, key: SortKey) => (
    <span className="flex w-full items-center justify-between select-none">
      <span>{label}</span>
      <span className="inline-block w-3 text-right">
        {sortKey === key ? (sortOrder === "asc" ? "▲" : "▼") : null}
      </span>
    </span>
  );

  if (listQuery.isLoading) {
    return (
      <>
        <div className="flex items-center">
          <h1 className="text-lg font-semibold md:text-2xl">Extractions</h1>
        </div>
        <div
          className="flex flex-1 items-center justify-center rounded-lg border border-dashed shadow-sm"
          x-chunk="dashboard-02-chunk-1"
        >
          <div className="flex flex-col items-center gap-1 text-center">
            <p className="text-sm text-muted-foreground">
              Loading extractions...
            </p>
          </div>
        </div>
      </>
    );
  }

  const hasResults = (listQuery.data?.results?.length ?? 0) > 0;
  const hasDateFilter = !!dateFrom || !!dateTo;

  return (
    <>
      <div className="w-full flex justify-between items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Extractions</h1>
        <div className="flex items-end gap-4">
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            disabled={exportInProgress}
          >
            <Download className="h-4 w-4 mr-2" />
            {exportInProgress ? "Exporting…" : "Export"}
          </Button>
          <div>
            <Label htmlFor="date_from">From</Label>
            <Input
              id="date_from"
              type="date"
              value={dateFrom || ""}
              onChange={(e) => handleDateChange("from", e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="date_to">To</Label>
            <Input
              id="date_to"
              type="date"
              value={dateTo || ""}
              onChange={(e) => handleDateChange("to", e.target.value)}
            />
          </div>
        </div>
      </div>
      {hasResults ? (
        <Card>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => handleSort("catalogue")}
                  >
                    {renderHeader("Catalogue", "catalogue")}
                  </TableHead>
                  <TableHead>Recipe</TableHead>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => handleSort("type")}
                  >
                    {renderHeader("Type", "type")}
                  </TableHead>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => handleSort("status")}
                  >
                    {renderHeader("Status", "status")}
                  </TableHead>
                  <TableHead>
                    <span>Stats</span>
                  </TableHead>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => handleSort("cost")}
                  >
                    {renderHeader("Cost", "cost")}
                  </TableHead>
                  <TableHead>Extracted Items</TableHead>
                  <TableHead
                    className="cursor-pointer"
                    onClick={() => handleSort("date")}
                  >
                    {renderHeader("Date", "date")}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(listQuery.data?.results || []).map((extraction) => (
                  <ExtractionListItem
                    key={extraction.id}
                    extraction={extraction}
                    onOpen={(id) => navigate(`/${id}`)}
                  />
                ))}
              </TableBody>
            </Table>
          </CardContent>
          <CardFooter>
            <PaginationButtons
              totalItems={listQuery.data!.totalItems}
              totalPages={listQuery.data!.totalPages}
            />
          </CardFooter>
        </Card>
      ) : (
        <div
          className="flex flex-1 items-center justify-center rounded-lg border border-dashed shadow-sm"
          x-chunk="dashboard-02-chunk-1"
        >
          <div className="flex flex-col items-center gap-1 text-center">
            <h3 className="text-2xl font-bold tracking-tight">
              {hasDateFilter
                ? "No extractions match your filter"
                : "No extractions have been created yet!"}
            </h3>
            <p className="text-sm text-muted-foreground">
              {hasDateFilter
                ? "Try adjusting your date range."
                : "Select a catalogue to start an extraction."}
            </p>
            {!hasDateFilter && (
              <Link to="~/catalogues">
                <Button className="mt-4">
                  <Earth className="h-5 w-5 mr-2" />
                  Catalogues
                </Button>
              </Link>
            )}
          </div>
        </div>
      )}
    </>
  );
}
