import type { TableColumnsType } from "antd";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ResizableTable from "@/components/ui/resizable-table";
import type { DiscoveredPage, DiscoveredPageLabel } from "@/domain";
import { crawlRuns, discoveredPages } from "@/mock-control-plane";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function CrawlRunDetail() {
    const { runId } = useParams<{ runId: string }>();
    // TODO(crawl-db): Load this crawl run and its latest persisted crawl + discovery progress/metrics from PostgreSQL.
    // TODO(blob-store): Resolve the crawl cache artifact path and cached-page inventory from blob storage.
    // TODO(discovery-db): Load discovered/classified pages only for this exact crawlRunId. Never combine pages across crawl caches.
    const run = crawlRuns.find((item) => item.id === runId);
    if (!run) return <div>Crawl run not found.</div>;

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
                <div>
                    <div className="font-medium">{page.title}</div>
                    <div className="max-w-[700px] truncate text-xs text-muted-foreground">
                        {page.url}
                    </div>
                </div>
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
                <div className="flex flex-wrap gap-1">
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
                </div>
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
        <div className="space-y-6">
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
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold">{run.id}</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {run.sourceName} ·{" "}
                        {new Date(crawlTimestamp).toLocaleString()} ·{" "}
                        {run.strategyName}
                    </p>
                    <p className="mt-2 max-w-4xl break-all text-sm">
                        <span className="text-muted-foreground">
                            Blob path:{" "}
                        </span>
                        {run.cachePath ??
                            "Not available until the crawl succeeds"}
                    </p>
                </div>
                <div className="flex items-center gap-2">
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
                </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Discovery</CardTitle>
                    <p className="text-sm text-muted-foreground">
                        Discovery is not automatic. Open it when this crawl
                        cache is ready to classify.
                    </p>
                </CardHeader>
                <CardContent className="grid gap-4 sm:grid-cols-3">
                    <div>
                        <div className="text-xs text-muted-foreground">
                            Status
                        </div>
                        <div className="mt-1 font-medium">{discoveryLabel}</div>
                    </div>
                    <div>
                        <div className="text-xs text-muted-foreground">
                            Classified pages
                        </div>
                        <div className="mt-1 font-medium">
                            {run.pagesClassified ?? classifiedPages.length}
                        </div>
                    </div>
                    <div>
                        <div className="text-xs text-muted-foreground">
                            Interesting pages
                        </div>
                        <div className="mt-1 font-medium">
                            {run.interestingPages ?? interestingPages.length}
                        </div>
                    </div>
                </CardContent>
            </Card>

            {run.discoveryStatus !== "not_started" && (
                <section
                    aria-labelledby="crawl-discovered-pages-heading"
                    className="space-y-3"
                >
                    <div>
                        <h2
                            id="crawl-discovered-pages-heading"
                            className="text-base font-semibold"
                        >
                            Discovered pages
                        </h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Classifications belong only to this timestamped
                            crawl cache ·{" "}
                            {new Date(crawlTimestamp).toLocaleString()}.
                        </p>
                    </div>
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
                </section>
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
        </div>
    );
}
