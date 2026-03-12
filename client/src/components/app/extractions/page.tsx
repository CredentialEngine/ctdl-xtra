import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { JsonView } from "@/components/ui/jsonview";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { concisePrintDate, prettyPrintDate, resolveCrawlPageUrl, trpc } from "@/utils";
import { ExternalLink } from "lucide-react";
import { useState } from "react";
import { useParams } from "wouter";
import { base64Img } from "./utils";

export default function CrawlPageDetail() {
  const { extractionId, stepId, crawlPageId } = useParams();
  const crawlPageQuery = trpc.extractions.crawlPageDetail.useQuery(
    { crawlPageId: parseInt(crawlPageId || "") },
    { enabled: !!crawlPageId }
  );
  const crawlPageLogsQuery = trpc.extractions.crawlPageLogs.useQuery(
    { crawlPageId: parseInt(crawlPageId || "") },
    { enabled: !!crawlPageId }
  );
  const simulateExtractionQuery =
    trpc.extractions.simulateDataExtraction.useMutation();
  const [simulatedExtractedData, setSimulatedExtractedData] =
    useState<
      Awaited<ReturnType<
        (typeof simulateExtractionQuery)["mutateAsync"]
      > | null>
    >(null);
  if (!crawlPageQuery.data) {
    return null;
  }

  const onSimulateDataExtraction = async () => {
    const simulatedData = await simulateExtractionQuery.mutateAsync({
      crawlPageId: parseInt(crawlPageId || ""),
    });
    if (simulatedData) {
      setSimulatedExtractedData(simulatedData);
    }
  };

  const item = crawlPageQuery.data;

  const breadCrumbs = [
    { label: "Extractions", href: "/" },
    { label: `Extraction #${extractionId}`, href: `/${extractionId}` },
    {
      label: `Step #${stepId}`,
      href: `/${extractionId}/steps/${stepId}`,
    },
    {
      label: `Step Item #${crawlPageId}`,
      href: `/${extractionId}/steps/${stepId}/items/${item.crawlPage.id}`,
    },
  ];

  const dataItems = item.dataItems ?? [];

  const tabTriggers = [
    <TabsTrigger key="data" value="data">Data</TabsTrigger>,
    <TabsTrigger key="raw_content" value="raw_content">Raw content</TabsTrigger>,
  ];
  const tabContents = [
    <TabsContent key="data" value="data">
      {dataItems.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Dataset ID</TableHead>
              <TableHead>Crawl Page ID</TableHead>
              <TableHead>Created At</TableHead>
              <TableHead>Content (JSON)</TableHead>
              <TableHead>Text Inclusion</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {dataItems.map((di) => (
              <TableRow key={di.id}>
                <TableCell className="text-sm">{di.id}</TableCell>
                <TableCell className="text-sm">{di.datasetId}</TableCell>
                <TableCell className="text-sm">{di.crawlPageId}</TableCell>
                <TableCell className="text-sm">
                  {prettyPrintDate(di.createdAt)}
                </TableCell>
                <TableCell className="max-w-md">
                  <JsonView data={di.structuredData} initialExpanded={true} />
                </TableCell>
                <TableCell className="max-w-md">
                  {di.textInclusion != null ? (
                    <JsonView data={di.textInclusion} initialExpanded={false} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : (
        <div className="text-muted-foreground">
          No data items yet. They will appear here once the data extraction has
          run for this page.
        </div>
      )}
    </TabsContent>,
    <TabsContent key="raw_content" value="raw_content">
      <code>{item.content}</code>
    </TabsContent>,
  ];

  const defaultTab = "data";

  if (item.markdownContent) {
    tabTriggers.push(
      <TabsTrigger key="simplified_content" value="simplified_content">Simplified Content</TabsTrigger>
    );
    tabContents.push(
      <TabsContent key="simplified_content" value="simplified_content">
        <pre className="whitespace-pre-wrap break-all">
          {item.markdownContent}
        </pre>
      </TabsContent>
    );
  }

  tabTriggers.push(
    <TabsTrigger key="operation_logs" value="operation_logs">Operation logs</TabsTrigger>
  );
  const pageLogs = crawlPageLogsQuery.data ?? [];
  tabContents.push(
    <TabsContent key="operation_logs" value="operation_logs">
      <div className="space-y-4">
        {pageLogs.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Type</TableHead>
                <TableHead>Message</TableHead>
                <TableHead>Created At</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pageLogs.map((log) => (
                <TableRow key={log.id}>
                  <TableCell>{log.logLevel}</TableCell>
                  <TableCell className="max-w-md overflow-hidden text-ellipsis whitespace-nowrap" title={log.log}>
                    {log.log}
                  </TableCell>
                  <TableCell>{concisePrintDate(log.createdAt)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
        {item.crawlPage.fetchFailureReason ? (
          <Accordion type="single" collapsible={true}>
            <AccordionItem value="advanced_error_details">
              <AccordionTrigger>Advanced Error Details</AccordionTrigger>
              <AccordionContent>
                <pre>
                  {JSON.stringify(item.crawlPage.fetchFailureReason, null, 2)}
                </pre>
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        ) : !crawlPageLogsQuery.isLoading && pageLogs.length === 0 ? (
          <div className="text-muted-foreground">No content to display.</div>
        ) : null}
      </div>
    </TabsContent>
  );

  const screenshot = item.screenshot ? base64Img(item.screenshot) : null;
  if (screenshot) {
    tabTriggers.splice(1, 0, <TabsTrigger key="screenshot" value="screenshot">Screenshot</TabsTrigger>);
    tabContents.splice(1, 0, <TabsContent key="screenshot" value="screenshot">{screenshot}</TabsContent>);
  }

  const formattedSimulatedData = simulatedExtractedData?.data
    ? JSON.stringify(simulatedExtractedData?.data, null, 2)
    : null;

  return (
    <>
      <BreadcrumbTrail items={breadCrumbs} />

      {item.content ? (
        <div>
          <Button
            className="mb-4"
            onClick={onSimulateDataExtraction}
            disabled={simulateExtractionQuery.isLoading}
          >
            Simulate data extraction
          </Button>
          {formattedSimulatedData ? (
            <Accordion type="single" collapsible={true}>
              <AccordionItem value="simulated_data">
                <AccordionTrigger>Simulated Data</AccordionTrigger>
                <AccordionContent>
                  <Tabs defaultValue="output">
                    <TabsList>
                      <TabsTrigger value="output">Output</TabsTrigger>
                      <TabsTrigger value="prompt">Prompt</TabsTrigger>
                    </TabsList>
                    <TabsContent value="output">
                      <pre className="text-xs overflow-auto">
                        {formattedSimulatedData}
                      </pre>
                    </TabsContent>
                    <TabsContent value="prompt">
                      <pre className="text-xs overflow-auto">
                        {simulatedExtractedData?.prompt}
                      </pre>
                    </TabsContent>
                  </Tabs>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          ) : null}
        </div>
      ) : null}

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold md:text-2xl">
          Extraction Step Item #{crawlPageId} - Content Preview
        </h1>
        {item.crawlPage.url && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const url = item.crawlPage.url;
              const baseUrl = item.crawlPage.extraction?.recipe?.url;
              const resolved = baseUrl
                ? resolveCrawlPageUrl(url, baseUrl)
                : url;
              window.open(resolved, "_blank", "noopener,noreferrer");
            }}
          >
            <ExternalLink className="w-4 h-4 mr-2" />
            Open Page URL
          </Button>
        )}
      </div>

      <Tabs defaultValue={defaultTab}>
        <TabsList className="w-full mb-4">{tabTriggers}</TabsList>
        <div className="border border-dashed p-4 text-xs overflow-auto">
          {tabContents}
        </div>
      </Tabs>
    </>
  );
}
