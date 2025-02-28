import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { concisePrintDate, trpc } from "@/utils";
import { PageType } from "@common/types";
import { Link, useParams } from "wouter";
import usePagination from "../usePagination";
import { displayStepType } from "./utils";

function displayDataType(dataType: PageType) {
  switch (dataType) {
    case PageType.DETAIL:
      return "Detail Page";
    case PageType.CATEGORY_LINKS:
      return "Category Page";
    case PageType.DETAIL_LINKS:
      return "Detail Links Page";
  }
}

export default function CrawlStepDetail() {
  let { extractionId, stepId } = useParams();
  const { page, PaginationButtons } = usePagination();
  const extractionQuery = trpc.extractions.detail.useQuery(
    { id: parseInt(extractionId || "") },
    { enabled: !!extractionId }
  );
  const stepQuery = trpc.extractions.stepDetail.useQuery(
    { stepId: parseInt(stepId || ""), page },
    { enabled: !!extractionId && !!stepId }
  );

  if (!extractionQuery.data || !stepQuery.data) {
    return null;
  }

  const breadCrumbs = [
    { label: "Extractions", href: "/" },
    { label: `Extraction #${extractionId}`, href: `/${extractionId}` },
  ];

  const step = stepQuery.data.crawlStep;
  const items = stepQuery.data.crawlPages;

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />
      <div className="flex items-center">
        <h1 className="text-lg font-semibold md:text-2xl">
          Extraction Step #{step.id}
        </h1>
      </div>
      <div className="border p-4 rounded-md">
        <div className="text-sm text-muted-foreground mb-2">Step Type</div>
        <div>{displayStepType(step.step)}</div>
      </div>
      <Card>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Data Type</TableHead>
                <TableHead>Created At</TableHead>
                <TableHead>URL</TableHead>
                <TableHead>Content</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.results.map((item) => (
                <TableRow key={`step-item-${item.id}`}>
                  <TableCell>{item.id}</TableCell>
                  <TableCell>
                    {displayDataType(item.pageType as PageType)}
                  </TableCell>
                  <TableCell>{concisePrintDate(item.createdAt)}</TableCell>
                  <TableCell className="max-w-40 overflow-hidden whitespace-nowrap text-ellipsis text-blue-800 underline">
                    <a href={item.url} target="_blank">
                      {item.url}
                    </a>
                  </TableCell>
                  <TableCell>
                    {item.status == "SUCCESS" || item.status == "ERROR" ? (
                      <Button variant={"outline"} size={"sm"} asChild>
                        <Link
                          to={`/${extractionId}/steps/${stepId}/items/${item.id}`}
                        >
                          View
                        </Link>
                      </Button>
                    ) : null}
                  </TableCell>
                  <TableCell>{item.status}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
        {items.results.length > 0 ? (
          <CardFooter>
            <PaginationButtons
              totalItems={items.totalItems}
              totalPages={items.totalPages}
            />
          </CardFooter>
        ) : null}
      </Card>
    </>
  );
}
