import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer } from "@/components/ui/chart";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import JsonPopover from "@/components/ui/jsonPopover";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tree, TreeNode } from "@/components/ui/tree";
import { useToast } from "@/components/ui/use-toast";
import {
  CrawlStep,
  ExtractionStatus,
  RecipeDetectionStatus,
  concisePrintDate,
  prettyPrintDate,
  trpc,
} from "@/utils";
import { CookingPot, LibraryBig, List } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, XAxis, YAxis } from "recharts";
import { Link, useLocation, useParams } from "wouter";
import { displayRecipeDetails } from "../recipes/util";
import { displayStepType } from "./utils";

function displayStepParent(steps: CrawlStep[], parentId: number) {
  const parent = steps.find((s) => s.id == parentId);
  if (!parent) {
    return parentId;
  }
  return displayStepType(parent.step);
}

function buildStepHierarchy(steps: CrawlStep[]): TreeNode[] {
  const stepMap = new Map<number, TreeNode>();
  const rootNodes: TreeNode[] = [];

  // First pass: create all step nodes
  steps.forEach((step) => {
    const stepType = displayStepType(step.step);
    const stepWithPages = step as CrawlStep & { crawlPages?: Array<{ id: number; url: string; crawlStepId: number }> };
    const crawlPages = stepWithPages.crawlPages || [];
    
    // Create page nodes as children
    const pageNodes: TreeNode[] = crawlPages.map((page) => ({
      id: `page-${page.id}`,
      label: page.url,
      children: [],
      type: 'page',
      page: page,
      url: page.url,
    }));

    const node: TreeNode = {
      id: step.id,
      label: `Step ${step.id}: ${stepType}`,
      children: pageNodes,
      type: 'step',
      step: step,
    };
    stepMap.set(step.id, node);
  });

  // Second pass: build step hierarchy
  steps.forEach((step) => {
    const node = stepMap.get(step.id)!;
    if (step.parentStepId === null || step.parentStepId === undefined) {
      rootNodes.push(node);
    } else {
      const parent = stepMap.get(step.parentStepId);
      if (parent) {
        // Separate child steps and pages
        const existingChildSteps = (parent.children || []).filter((c) => c.type === 'step');
        const existingPages = (parent.children || []).filter((c) => c.type === 'page');
        // Add the new child step, then keep existing pages
        parent.children = [...existingChildSteps, node, ...existingPages];
      } else {
        // Parent not found, treat as root
        rootNodes.push(node);
      }
    }
  });

  return rootNodes;
}

function getElapsedTimeText(statsLastUpdatedAt: string, createdAt: string) {
  const elapsedMs =
    new Date(statsLastUpdatedAt).getTime() - new Date(createdAt).getTime();
  const elapsedHours = Math.floor(elapsedMs / (1000 * 60 * 60));
  const elapsedMinutes = Math.floor(
    (elapsedMs % (1000 * 60 * 60)) / (1000 * 60)
  );
  const elapsedSeconds = Math.floor((elapsedMs % (1000 * 60)) / 1000);

  if (elapsedHours > 0) {
    return `${elapsedHours}hr${elapsedMinutes}mins`;
  } else if (elapsedMinutes > 0) {
    return `${elapsedMinutes}mins`;
  } else {
    return `${elapsedSeconds}s`;
  }
}

const REFETCH_STATES = [
  ExtractionStatus.IN_PROGRESS,
  ExtractionStatus.WAITING
];

export default function ExtractionDetail() {
  const { extractionId } = useParams();
  const extractionIdNum = parseInt(extractionId || "");
  const [lockedCancel, setLockedCancel] = useState(true);
  const [lockedDelete, setLockDelete] = useState(true);
  const { toast } = useToast();
  const [, navigate] = useLocation();
  const query = trpc.extractions.detail.useQuery(
    { id: extractionIdNum },
    { 
      enabled: !!extractionIdNum,
      refetchInterval(data) {
        if (REFETCH_STATES.includes(data?.status as ExtractionStatus)) {
          return 10000;
        }
        return false;
      },
    }
  );
  const errorPagesQuery = trpc.extractions.errorPages.useQuery(
    { extractionId: extractionIdNum },
    { enabled: !!extractionIdNum }
  );
  const cancelExtraction = trpc.extractions.cancel.useMutation();
  const destroyExtraction = trpc.extractions.destroy.useMutation();
  const retryFailed = trpc.extractions.retryFailed.useMutation();

  if (!query.data) {
    return null;
  }

  const onCancelExtraction = async () => {
    if (lockedCancel) {
      return;
    }
    await cancelExtraction.mutateAsync({ id: extraction.id });
    toast({
      title: "Extraction cancelled",
      description: "The extraction has been cancelled.",
    });
    navigate("/");
  };

  const onRetryFailed = async () => {
    try {
      await retryFailed.mutateAsync({
        id: extraction.id,
      });
      toast({
        title: "Retrying failed items",
        description: "We are retrying the failed items for this extraction.",
      });
      await query.refetch();
    } catch (err: unknown) {
      let errorMessage =
        "Something wrong when retrying the items. Please notify us about it.";
      if (err instanceof Error && err.message) {
        errorMessage = err.message;
      }
      toast({
        title: "Error retrying items",
        description: errorMessage,
      });
    }
  };

  const onDestroyExtraction = async () => {
    if (lockedDelete) {
      return;
    }
    await destroyExtraction.mutateAsync({ id: query.data!.id });
    toast({
      title: "Extraction deleted",
      description: "The extraction has been deleted successfully.",
    });
    navigate("/");
  };

  const extraction = query.data;
  let totalDownloads = 0,
    totalDownloadsAttempted = 0,
    totalDownloadErrors = 0,
    totalExtractionsPossible = 0,
    totalExtractionsAttempted = 0,
    totalExtractionErrors = 0,
    totalItems = 0;
  for (const step of extraction.completionStats?.steps || []) {
    totalDownloads += step.downloads.total;
    totalDownloadsAttempted += step.downloads.attempted;
    totalDownloadErrors += step.downloads.attempted - step.downloads.succeeded;
    totalExtractionsPossible += step.downloads.succeeded;
    totalExtractionsAttempted += step.extractions.attempted;
    totalExtractionErrors +=
      step.extractions.attempted - step.extractions.succeeded;
    totalItems += step.extractions.courses;
  }

  // if we dont have a generated at, just use the current date
  const elapsedTimeText = getElapsedTimeText(
    extraction.completionStats?.generatedAt || new Date().toISOString(),
    extraction.createdAt
  );

  let statusDetails = null;

  if (extraction.status == ExtractionStatus.COMPLETE) {
    statusDetails = (
      <div>
        Completed at {prettyPrintDate(extraction.completionStats!.generatedAt)}.
        <div className="text-sm text-muted-foreground mt-2">
          Took {elapsedTimeText}
        </div>
      </div>
    );
  } else if (
    extraction.status == ExtractionStatus.CANCELLED ||
    extraction.status == ExtractionStatus.STALE
  ) {
    if (extraction?.completionStats?.generatedAt) {
      statusDetails = (
        <div>
          Marked as stale on{" "}
          {prettyPrintDate(extraction.completionStats!.generatedAt)}.
          <div className="text-sm text-muted-foreground mt-2">
            Ran for {elapsedTimeText}
          </div>
        </div>
      );
    }
  } else {
    statusDetails = (
      <div className="text-sm text-muted-foreground mt-2">
        Running for {elapsedTimeText}
      </div>
    );
  }

  return (
    <>
      <div className="">
        <div className="flex gap-4">
          <Card className="w-1/2">
            <CardHeader>
              <CardTitle>Extraction Details</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="mb-4">
                <div>
                  Started at {prettyPrintDate(extraction.createdAt)}.{" "}
                  <Badge>{extraction.status}</Badge>
                </div>
                {statusDetails}
              </div>

              <div className="rounded-md border p-4 mt-2 flex items-center">
                {extraction.dataItemsCount ? (
                  <Link
                    to={`~/datasets/items/${extraction.id}`}
                    className="flex items-center gap-4 w-full"
                  >
                    <div>
                      <LibraryBig className="w-4 h-4" />
                    </div>
                    <div>View Data</div>
                  </Link>
                ) : (
                  <div>
                    <p>No data</p>
                    <div className="text-sm text-muted-foreground">
                      Check again later
                    </div>
                  </div>
                )}
              </div>
              {extraction.completionStats?.costs?.callSites?.length ? (
                <div className="rounded-md border p-4 mt-2">
                  <div className="text-sm text-muted-foreground mb-1">
                    Models used
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {[...
                      new Set(
                        extraction.completionStats.costs.callSites.map(
                          (c) => c.model
                        )
                      ),
                    ].map((m) => (
                      <Badge key={`model-${m}`}>{m}</Badge>
                    ))}
                  </div>
                </div>
              ) : null}
              <div className="rounded-md border p-4 mt-2">
                <Link
                  to={`~/catalogues/${extraction.recipe.catalogue.id}/recipes/${extraction.recipe.id}`}
                  className="flex items-center gap-4 w-full"
                >
                  <div>
                    <CookingPot className="w-4 h-4" />
                  </div>
                  <div>
                    Recipe #{extraction.recipe.id}{" "}
                    {extraction.recipe.status == RecipeDetectionStatus.SUCCESS
                      ? null
                      : "— Draft"}
                    <div className="text-xs">
                      {displayRecipeDetails(extraction.recipe)}
                    </div>
                    <div className="text-xs">
                      {extraction.recipe.url.substring(0, 200)}
                      ...
                    </div>
                  </div>
                </Link>
              </div>
              <div className="mt-4">
                {extraction.status == ExtractionStatus.IN_PROGRESS ? (
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button variant="destructive">Cancel extraction</Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>Are you absolutely sure?</DialogTitle>
                        <DialogDescription className="pt-2">
                          This action cannot be undone. This will cancel the
                          ongoing extraction and all its steps.
                        </DialogDescription>
                      </DialogHeader>
                      <div className="items-top flex space-x-2">
                        <Checkbox
                          id="cancel_extraction"
                          onCheckedChange={(e) => setLockedCancel(!e)}
                        />
                        <div className="grid gap-1.5 leading-none">
                          <label
                            htmlFor="cancel_extraction"
                            className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                          >
                            I understand the consequences
                          </label>
                          <Button
                            variant="destructive"
                            disabled={lockedCancel}
                            onClick={onCancelExtraction}
                            className="mt-4"
                          >
                            Cancel extraction
                          </Button>
                        </div>
                      </div>
                    </DialogContent>
                  </Dialog>
                ) : null}
                {extraction.status == ExtractionStatus.COMPLETE &&
                (totalDownloadErrors || totalExtractionErrors) ? (
                  <div className="mt-4 text-xs">
                    <Button
                      variant={"outline"}
                      size={"sm"}
                      onClick={onRetryFailed}
                      disabled={retryFailed.isLoading}
                    >
                      Retry failed items
                    </Button>
                  </div>
                ) : null}
                {extraction.status != ExtractionStatus.IN_PROGRESS ? (
                  <div className="mt-4">
                    <Dialog>
                      <DialogTrigger asChild>
                        <Button variant="destructive">Delete extraction</Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>Are you absolutely sure?</DialogTitle>
                          <DialogDescription className="pt-2">
                            This action cannot be undone. This will permanently
                            delete the extraction along with the extracted data.
                          </DialogDescription>
                        </DialogHeader>
                        <div className="items-top flex space-x-2">
                          <Checkbox
                            id="terms1"
                            onCheckedChange={(e) => setLockDelete(!e)}
                          />
                          <div className="grid gap-1.5 leading-none">
                            <label
                              htmlFor="terms1"
                              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                            >
                              I understand the consequences
                            </label>
                            <p className="text-sm text-muted-foreground">
                              Permanently delete the extraction and all its data
                            </p>
                            <Button
                              variant="destructive"
                              disabled={
                                lockedDelete || destroyExtraction.isLoading
                              }
                              onClick={onDestroyExtraction}
                              className="mt-4"
                            >
                              Delete extraction
                            </Button>
                          </div>
                        </div>
                      </DialogContent>
                    </Dialog>
                  </div>
                ) : null}
              </div>
            </CardContent>
          </Card>
          {extraction.completionStats ? (
            <Card className="w-1/2">
              <CardHeader>
                <CardTitle>Extraction Stats</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid auto-rows-min gap-2">
                  {totalItems ? (
                    <div className="flex items-baseline gap-1 text-2xl font-bold tabular-nums leading-none">
                      {totalItems}
                      <span className="text-sm font-normal">
                        Items extracted
                      </span>
                    </div>
                  ) : null}
                  <div className="flex items-baseline gap-1 text-2xl mt-4 font-bold tabular-nums leading-none">
                    {totalDownloadsAttempted}/{totalDownloads}
                    <span className="text-sm font-normal">Downloads</span>
                  </div>
                  <ChartContainer
                    config={{}}
                    className="aspect-auto h-[32px] w-full"
                  >
                    <BarChart
                      data={[
                        {
                          name: "Downloads",
                          value:
                            (totalDownloadsAttempted / totalDownloads) * 100,
                        },
                      ]}
                      layout="vertical"
                      margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
                    >
                      <Bar dataKey="value" radius={2} />
                      <YAxis type="category" hide />
                      <XAxis domain={[0, 100]} type="number" hide />
                    </BarChart>
                  </ChartContainer>
                </div>
                <div className="grid auto-rows-min gap-2 mt-4">
                  <div className="flex items-baseline gap-1 text-2xl font-bold tabular-nums leading-none">
                    {totalExtractionsAttempted}/{totalExtractionsPossible}
                    <span className="text-sm font-normal">
                      Page Extractions
                    </span>
                  </div>
                  <ChartContainer
                    config={{}}
                    className="aspect-auto h-[32px] w-full"
                  >
                    <BarChart
                      data={[
                        {
                          name: "Extractions",
                          value:
                            (totalExtractionsAttempted /
                              totalExtractionsPossible) *
                            100,
                        },
                      ]}
                      layout="vertical"
                      margin={{ top: 0, right: 0, left: 0, bottom: 0 }}
                    >
                      <Bar dataKey="value" radius={2} />
                      <YAxis type="category" hide />
                      <XAxis domain={[0, 100]} type="number" hide />
                    </BarChart>
                  </ChartContainer>
                </div>
                <div className="mt-2 gap-4">
                  {totalDownloadErrors ? (
                    <div className="text-xs text-muted-foreground py-1">
                      Download Errors: {totalDownloadErrors}
                    </div>
                  ) : null}
                  {totalExtractionErrors ? (
                    <div className="text-xs text-muted-foreground py-1">
                      Items not extracted: {totalExtractionErrors}
                    </div>
                  ) : null}
                </div>
                {errorPagesQuery.data && errorPagesQuery.data.length ? (
                  <div className="grid auto-rows-min gap-2 mt-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-baseline gap-1 text-2xl font-bold tabular-nums leading-none">
                        {errorPagesQuery.data.length}
                        <span className="text-sm font-normal">Errors</span>
                      </div>
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button size="sm" variant="outline">View</Button>
                        </DialogTrigger>
                        <DialogContent className="sm:max-w-[66vw] w-11/12 max-h-[70vh] overflow-y-auto">
                          <DialogHeader>
                            <DialogTitle>Error Pages</DialogTitle>
                            <DialogDescription>
                              Pages that failed to download and their error messages.
                            </DialogDescription>
                          </DialogHeader>
                          <div className="mt-2">
                            <Table>
                              <TableHeader>
                                <TableRow className="text-xs">
                                  <TableHead className="w-1/2">Error</TableHead>
                                  <TableHead>URL</TableHead>
                                  <TableHead className="text-right">Action</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody className="text-xs">
                                {errorPagesQuery.data.map((p) => (
                                  <TableRow key={`error-page-${p.id}`}>
                                    <TableCell className="align-top">
                                      {p.fetchFailureReason?.reason || "-"}
                                    </TableCell>
                                    <TableCell className="break-all align-top">
                                      <a href={p.url} target="_blank" rel="noreferrer" className="underline">
                                        {p.url}
                                      </a>
                                    </TableCell>
                                    <TableCell className="text-right align-top">
                                      <Button variant={"outline"} size="sm" className="text-xs" asChild>
                                        <Link to={`/${extraction.id}/steps/${p.crawlStepId}/items/${p.id}`}>
                                          View item
                                        </Link>
                                      </Button>
                                    </TableCell>
                                  </TableRow>
                                ))}
                              </TableBody>
                            </Table>
                          </div>
                        </DialogContent>
                      </Dialog>
                    </div>
                  </div>
                ) : null}
                {extraction.completionStats.costs ? (
                  <div className="mt-4">
                    <Accordion type="single" collapsible>
                      <AccordionItem value="cost-breakdown">
                        <AccordionTrigger>Cost Breakdown</AccordionTrigger>
                        <AccordionContent>
                          <Table>
                            <TableHeader>
                              <TableRow className="text-xs">
                                <TableHead>Call Site</TableHead>
                                <TableHead>Model</TableHead>
                                <TableHead>Input Tokens</TableHead>
                                <TableHead>Output Tokens</TableHead>
                                <TableHead className="text-right">
                                  Est. Cost
                                </TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody className="text-xs">
                              {extraction.completionStats.costs.callSites.map(
                                (callSite) => (
                                  <TableRow key={`${callSite.callSite}-${callSite.model}`}>
                                    <TableCell>{callSite.callSite}</TableCell>
                                    <TableCell>{callSite.model}</TableCell>
                                    <TableCell>
                                      {callSite.totalInputTokens}
                                    </TableCell>
                                    <TableCell>
                                      {callSite.totalOutputTokens}
                                    </TableCell>
                                    <TableCell className="text-right">
                                      {callSite.estimatedCost.toFixed(2)}
                                    </TableCell>
                                  </TableRow>
                                )
                              )}
                            </TableBody>
                          </Table>
                          <div className="mt-2 text-xs text-muted-foreground">
                            <div>
                              Total Input Tokens:{" "}
                              {
                                extraction.completionStats.costs
                                  .totalInputTokens
                              }
                            </div>
                            <div>
                              Total Output Tokens:{" "}
                              {
                                extraction.completionStats.costs
                                  .totalOutputTokens
                              }
                            </div>
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    </Accordion>
                    <div className="mt-4">
                      <span className="text-xs">Estimated Total Cost:</span>{" "}
                      <span className="text-xl">
                        $
                        {extraction.completionStats.costs.estimatedCost.toFixed(
                          2
                        )}
                      </span>
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
        </div>
        <Card className="mt-4">
          <CardHeader>
            <CardTitle>Extraction Steps</CardTitle>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="table">
              <TabsList>
                <TabsTrigger value="table">Table</TabsTrigger>
                <TabsTrigger value="hierarchy">Hierarchy</TabsTrigger>
              </TabsList>
              <TabsContent value="table">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-20">Step ID</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Parent</TableHead>
                      <TableHead>Configuration</TableHead>
                      <TableHead>Started At</TableHead>
                      <TableHead className="text-right">Items</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {extraction.crawlSteps.map((step) => (
                      <TableRow key={`steps-${step.id}`}>
                        <TableCell className="font-medium w-20">
                          {step.id}
                        </TableCell>
                        <TableCell>{displayStepType(step.step)}</TableCell>
                        <TableCell>
                          {step.parentStepId
                            ? displayStepParent(
                                extraction.crawlSteps,
                                step.parentStepId
                              )
                            : null}
                        </TableCell>
                        <TableCell>
                          {step.configuration ? (
                            <JsonPopover jsonData={step.configuration} />
                          ) : null}
                        </TableCell>
                        <TableCell>{concisePrintDate(step.createdAt)}</TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant={"outline"}
                            size="sm"
                            className="text-xs"
                            asChild
                          >
                            <Link to={`/${extraction.id}/steps/${step.id}`}>
                              <List className="w-3.5 h-3.5 mr-2" />
                              View {step.itemCount} items
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TabsContent>
              <TabsContent value="hierarchy">
                <Tree
                  data={buildStepHierarchy(extraction.crawlSteps)}
                  onNodeClick={(node) => {
                    if (node.type === 'page' && node.page) {
                      const page = node.page as { id: number; crawlStepId: number };
                      navigate(`/${extraction.id}/steps/${page.crawlStepId}/items/${page.id}`);
                    } else if (node.type === 'step' && node.step) {
                      navigate(`/${extraction.id}/steps/${node.step.id}`);
                    }
                  }}
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
