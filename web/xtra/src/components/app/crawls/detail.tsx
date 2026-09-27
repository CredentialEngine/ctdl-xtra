import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
import type { TableColumnsType } from "antd";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ResizableTable from "@/components/ui/resizable-table";
import type { DiscoveredPage, DiscoveredPageLabel } from "@/domain";
import { crawlRuns, discoveredPages } from "@/mock-control-plane";
import Link from "@/components/ui/route-link";
import { useParams } from "next/navigation";

export default function CrawlRunDetail() {
    const { runId } = useParams<{ runId: string }>();
    // TODO(crawl-db): Load this crawl run and its latest persisted crawl + discovery progress/metrics from PostgreSQL.
    // TODO(blob-store): Resolve the crawl cache artifact path and cached-page inventory from blob storage.
    // TODO(discovery-db): Load discovered/classified pages only for this exact crawlRunId. Never combine pages across crawl caches.
    const run = crawlRuns.find((item) => item.id === runId);
    if (!run) return <Box>Crawl run not found.</Box>;

    const classifiedPages = discoveredPages.filter(
        (page) => page.crawlRunId === run.id,
    );
    const interestingPages = classifiedPages.filter(
        (page) =>
            !page.labels.includes("Ignore") &&
            !page.labels.includes("Unclassified"),
    );
    const discoveryLabel =
        run.discoveryStatus === "not_started"
            ? "Not started"
            : run.discoveryStatus[0].toUpperCase() +
              run.discoveryStatus.slice(1);
    const crawlTimestamp =
        run.cacheTimestamp ?? run.finishedAt ?? run.startedAt;

    const pageColumns: TableColumnsType<DiscoveredPage> = [
        {
            title: "Page",
            key: "page",
            sorter: {
                compare: (a, b) => a.title.localeCompare(b.title),
                multiple: 4,
            },
            render: (_, page) => (
                <Box>
                    <Box className="font-medium">{page.title}</Box>
                    <Box className="max-w-[700px] truncate text-xs text-muted-foreground">
                        {page.url}
                    </Box>
                </Box>
            ),
        },
        {
            title: "Labels",
            dataIndex: "labels",
            key: "labels",
            width: 240,
            filters: [
                ...new Set(classifiedPages.flatMap((page) => page.labels)),
            ].map((value) => ({ text: value, value })),
            onFilter: (value, page) =>
                page.labels.includes(String(value) as DiscoveredPageLabel),
            render: (labels: DiscoveredPageLabel[]) => (
                <Box className="flex flex-wrap gap-1">
                    {labels.map((label) => (
                        <Badge
                            key={label}
                            variant={
                                label === "Ignore" ? "secondary" : "outline"
                            }
                        >
                            {label}
                        </Badge>
                    ))}
                </Box>
            ),
        },
        {
            title: "Confidence",
            dataIndex: "confidence",
            key: "confidence",
            width: 130,
            sorter: {
                compare: (a, b) => (a.confidence ?? 0) - (b.confidence ?? 0),
                multiple: 2,
            },
            render: (value?: number) =>
                value == null ? "—" : `${Math.round(value * 100)}%`,
        },
    ];

    return (
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Sources", href: "/sources" },
                    { label: run.sourceName, href: `/sources/${run.sourceId}` },
                    {
                        label: new Date(crawlTimestamp).toLocaleString(),
                        href: `/crawls/${run.id}`,
                    },
                ]}
            />
            <Box className="flex flex-wrap items-start justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        {run.id}
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        {run.sourceName} ·{" "}
                        {new Date(crawlTimestamp).toLocaleString()} ·{" "}
                        {run.strategyName}
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-2 max-w-4xl break-all text-sm"
                    >
                        <MuiTypography
                            component="span"
                            className="text-muted-foreground"
                        >
                            Blob path:{" "}
                        </MuiTypography>
                        {run.cachePath ??
                            "Not available until the crawl succeeds"}
                    </MuiTypography>
                </Box>
                <Box className="flex items-center gap-2">
                    <Button variant="outline" asChild>
                        <Link href={`/sources/${run.sourceId}`}>
                            Back to Source
                        </Link>
                    </Button>
                    {run.status === "succeeded" && (
                        <Button asChild>
                            <Link href={`/crawls/${run.id}/discovery`}>
                                {run.discoveryStatus === "not_started"
                                    ? "Open discovery"
                                    : "Review discovery"}
                            </Link>
                        </Button>
                    )}
                </Box>
            </Box>

            <Box className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Crawl status</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <Badge>
                            {run.status === "succeeded"
                                ? "Completed"
                                : run.status}
                        </Badge>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Progress</CardTitle>
                    </CardHeader>
                    <CardContent className="text-2xl font-semibold">
                        {run.progressPercent}%
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Pages crawled</CardTitle>
                    </CardHeader>
                    <CardContent className="text-2xl font-semibold">
                        {run.pagesCrawled}
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Failed pages</CardTitle>
                    </CardHeader>
                    <CardContent className="text-2xl font-semibold">
                        {run.pagesFailed}
                    </CardContent>
                </Card>
            </Box>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Discovery</CardTitle>
                    <MuiTypography
                        component="p"
                        className="text-sm text-muted-foreground"
                    >
                        Discovery is not automatic. Open it when this crawl
                        cache is ready to classify.
                    </MuiTypography>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-3">
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Status
                        </Box>
                        <Box className="mt-1 font-medium">{discoveryLabel}</Box>
                    </Box>
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Classified pages
                        </Box>
                        <Box className="mt-1 font-medium">
                            {run.pagesClassified ?? classifiedPages.length}
                        </Box>
                    </Box>
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Interesting pages
                        </Box>
                        <Box className="mt-1 font-medium">
                            {run.interestingPages ?? interestingPages.length}
                        </Box>
                    </Box>
                </CardContent>
            </Card>

            {run.discoveryStatus !== "not_started" && (
                <MuiBox
                    component="section"
                    aria-labelledby="crawl-discovered-pages-heading"
                    className="space-y-3"
                >
                    <Box>
                        <MuiTypography
                            variant="h2"
                            component="h2"
                            id="crawl-discovered-pages-heading"
                            className="text-base font-semibold"
                        >
                            Discovered pages
                        </MuiTypography>
                        <MuiTypography
                            component="p"
                            className="mt-1 text-sm text-muted-foreground"
                        >
                            Classifications belong only to this timestamped
                            crawl cache ·{" "}
                            {new Date(crawlTimestamp).toLocaleString()}.
                        </MuiTypography>
                    </Box>
                    <ResizableTable<DiscoveredPage>
                        ariaLabel={`Discovered pages for crawl ${run.id}`}
                        rowKey="id"
                        size="middle"
                        dataSource={classifiedPages}
                        columns={pageColumns}
                        locale={{
                            emptyText:
                                "No discovered pages for this crawl yet.",
                        }}
                        pagination={{
                            defaultPageSize: 25,
                            showSizeChanger: true,
                        }}
                    />
                </MuiBox>
            )}

            {run.error && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Failure</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-destructive">
                        {run.error}
                    </CardContent>
                </Card>
            )}
            {run.discoveryError && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">
                            Discovery failure
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-destructive">
                        {run.discoveryError}
                    </CardContent>
                </Card>
            )}
        </Box>
    );
}
