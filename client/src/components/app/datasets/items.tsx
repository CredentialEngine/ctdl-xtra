import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { JsonView } from "@/components/ui/jsonview";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { API_URL } from "@/constants";
import { DataItem, prettyPrintDate, trpc } from "@/utils";
import { Download } from "lucide-react";
import { useState } from "react";
import { useParams } from "wouter";
import { CourseStructuredData } from "../../../../../common/types";
import usePagination from "../usePagination";

interface CourseDisplayItemProps {
  item: DataItem;
}

function CourseDisplayItem({ item }: CourseDisplayItemProps) {
  const structuredData = item.structuredData as
    | CourseStructuredData
    | undefined;

  if (!structuredData) {
    return (
      <TableRow>
        <TableCell colSpan={5}>No data.</TableCell>
      </TableRow>
    );
  }

  return (
    <TableRow>
      <TableCell className="text-sm">{item.id}</TableCell>
      <TableCell className="text-sm">
        <JsonView data={item.structuredData} initialExpanded={true} />
      </TableCell>
    </TableRow>
  );
}

export default function DatasetItems() {
  const { extractionId } = useParams();
  const [downloadInProgress, setDownloadInProgress] = useState(false);
  const { page, PaginationButtons } = usePagination();

  const extractionQuery = trpc.extractions.detail.useQuery(
    { id: parseInt(extractionId || "") },
    { enabled: !!extractionId }
  );

  const itemsQuery = trpc.datasets.items.useQuery(
    { extractionId: parseInt(extractionId || ""), page },
    { enabled: !!extractionId }
  );

  if (!extractionQuery.data || !itemsQuery.data) {
    return null;
  }
  const handleDownload: React.MouseEventHandler<HTMLButtonElement> = (e) => {
    setDownloadInProgress(true);
    e.preventDefault();
    fetch(`${API_URL}/downloads/bulk_upload_template/${extractionId}`, {
      credentials: "include",
    })
      .then((response) => {
        const disposition = response.headers.get("Content-Disposition");
        let filename = `AICourseMapping-BulkUploadTemplate-${extractionId}.csv`; // Fallback filename

        if (disposition && disposition.includes("attachment")) {
          const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
          const matches = filenameRegex.exec(disposition);
          if (matches != null && matches[1]) {
            filename = matches[1].replace(/['"]/g, "");
          }
        }

        return response.blob().then((blob) => ({
          blob,
          filename,
        }));
      })
      .then(({ blob, filename }) => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        setDownloadInProgress(false);
      })
      .catch((err) => {
        console.error("Download error:", err);
        setDownloadInProgress(false);
      });
  };

  const extraction = extractionQuery.data;
  const catalogue = extraction.recipe.catalogue;
  const items = itemsQuery.data.results;

  const breadCrumbs = [
    { label: "Data Library", href: "/" },
    { label: `Catalogue #${catalogue.id}`, href: `/catalogue/${catalogue.id}` },
    {
      label: `Extraction ${extraction.id}`,
      href: `~/extractions/${extraction.id}`,
    },
  ];

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">
          Extraction #{extraction.id} Data - {catalogue.catalogueType}
        </h1>
      </div>
      <div className="border p-6">
        <div className="flex gap-10">
          <div>
            <div className="font-semibold">Catalogue</div>
            <div className="text-sm">{extraction.recipe.catalogue.name}</div>
            <div className="font-semibold mt-4">Recipe URL</div>
            <div className="text-sm">
              <a href={extraction.recipe.url} target="_blank">
                {extraction.recipe.url}
              </a>
            </div>
          </div>
          <div>
            <div className="font-semibold mb-4">Downloads</div>
            <Button onClick={handleDownload} disabled={downloadInProgress}>
              <Download className="w-4 h-4 mr-2" />
              Download bulk-upload template
            </Button>
          </div>
        </div>
        <div className="mt-6 border-t border-border pt-6 text-sm">
          {itemsQuery.data.totalItems} items were extracted. The extraction was
          created on {prettyPrintDate(extraction.createdAt)}.
          <Badge className="ml-2">{extraction.status}</Badge>
        </div>
      </div>
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data ID</TableHead>
                <TableHead>Data</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <CourseDisplayItem key={`step-item-${item.id}`} item={item} />
              ))}
            </TableBody>
          </Table>
        </CardContent>
        {items.length > 0 ? (
          <CardFooter>
            <PaginationButtons
              totalItems={itemsQuery.data.totalItems}
              totalPages={itemsQuery.data.totalPages}
            />
          </CardFooter>
        ) : null}
      </Card>
    </>
  );
}
