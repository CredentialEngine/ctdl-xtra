import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCallback, useEffect, useMemo, useState } from "react";
import { IterableElement, prettyPrintDate, RouterOutput, trpc } from "@/utils";
import { Earth } from "lucide-react";
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
import usePagination from "../usePagination";

type ExtractionSummary = IterableElement<
  RouterOutput["extractions"]["list"]["results"]
>;

type SortKey = "catalogue" | "type" | "status" | "date";
type SortOrder = "asc" | "desc";

const VALID_SORT_KEYS: SortKey[] = ["catalogue", "type", "status", "date"];

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
  return currentKey === clickedKey
    ? currentOrder === "asc"
      ? "desc"
      : "asc"
    : clickedKey === "date"
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

const ExtractionListItem = (extraction: ExtractionSummary) => {
  const catalogue = extraction.recipe.catalogue;
  let totalDownloads = 0,
    totalDownloadsAttempted = 0,
    totalExtractionsPossible = 0,
    totalExtractionsAttempted = 0;
  for (const step of extraction.completionStats?.steps || []) {
    totalDownloads += step.downloads.total;
    totalDownloadsAttempted += step.downloads.attempted;
    totalExtractionsPossible += step.downloads.succeeded;
    totalExtractionsAttempted += step.extractions.attempted;
    step.extractions.attempted - step.extractions.succeeded;
  }
  return (
    <TableRow>
      <TableCell colSpan={2} className="">
        <Link to={`/${extraction.id}`}>
          <div className="flex items-center gap-4">
            {catalogue?.thumbnailUrl ? (
              <img src={catalogue.thumbnailUrl} style={{ maxHeight: "30px" }} />
            ) : null}
            {catalogue?.name || "Unknown"}
          </div>
        </Link>
      </TableCell>
      <TableCell className="font-medium">
        <Link to={`/${extraction.id}`}>{catalogue?.catalogueType || "-"}</Link>
      </TableCell>
      <TableCell className="text-xs">{extraction.status}</TableCell>
      <TableCell className="text-xs">
        {extraction.completionStats
          ? totalDownloads > 0
            ? `${Math.floor((totalDownloadsAttempted / totalDownloads) * 100)}%`
            : "0%"
          : "Pending"}
      </TableCell>
      <TableCell className="text-xs">
        {extraction.completionStats
          ? totalExtractionsPossible > 0
            ? `${Math.floor((totalExtractionsAttempted / totalExtractionsPossible) * 100)}%`
            : "0%"
          : "Pending"}
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
            <p className="text-sm text-muted-foreground">Loading extractions...</p>
          </div>
        </div>
      </>
    );
  }

  if (!listQuery.data?.results.length) {
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
            <h3 className="text-2xl font-bold tracking-tight">
              No extractions have been created yet!
            </h3>
            <p className="text-sm text-muted-foreground">
              Select a catalogue to start an extraction.
            </p>
            <Link to="~/catalogues">
              <Button className="mt-4">
                <Earth className="h-5 w-5 mr-2" />
                Catalogues
              </Button>
            </Link>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="w-full flex justify-between items-center">
        <h1 className="text-lg font-semibold md:text-2xl">Extractions</h1>
        <div className="flex items-end gap-4">
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
      <Card>
        <CardContent className="px-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead
                  colSpan={2}
                  className="cursor-pointer"
                  onClick={() => handleSort("catalogue")}
                >
                  {renderHeader("Catalogue", "catalogue")}
                </TableHead>
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
                  <span>Downloads</span>
                </TableHead>
                <TableHead>
                  <span>Extractions</span>
                </TableHead>
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
                <ExtractionListItem key={extraction.id} {...extraction} />
              )) || (
                <TableRow>
                  <TableCell colSpan={3}>
                    <div className="flex items-center justify-center">
                      Loading extractions...
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
        {listQuery.data!.results.length > 0 ? (
          <CardFooter>
            <PaginationButtons
              totalItems={listQuery.data.totalItems}
              totalPages={listQuery.data.totalPages}
            />
          </CardFooter>
        ) : null}
      </Card>
    </>
  );
}
