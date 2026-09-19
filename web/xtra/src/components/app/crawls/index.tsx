import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import ResizableTable from "@/components/ui/resizable-table";
import { crawlRuns } from "@/mock-control-plane";
import type { CrawlRun } from "@/domain";
import Link from "@/components/ui/route-link";

function RunStatus({ status }: { status: CrawlRun["status"] }) {
    const variant =
        status === "failed"
            ? "destructive"
            : status === "succeeded"
              ? "default"
              : "secondary";
    return (
        <Badge variant={variant}>
            {status === "succeeded"
                ? "Completed"
                : status[0].toUpperCase() + status.slice(1)}
        </Badge>
    );
}

function DiscoveryStatus({ status }: { status: CrawlRun["discoveryStatus"] }) {
    const variant =
        status === "failed"
            ? "destructive"
            : status === "succeeded"
              ? "default"
              : "secondary";
    const label =
        status === "not_started"
            ? "Not started"
            : status[0].toUpperCase() + status.slice(1);
    return <Badge variant={variant}>{label}</Badge>;
}

export default function CrawlRuns() {
    // TODO(crawl-db): Load crawl runs, immutable crawl strategy snapshots, progress, cache artifact refs, errors, and timestamps from PostgreSQL.
    // TODO(argo-events): Argo workflow callbacks update crawl run status/progress in the API; the UI reads that persisted state.
    const rows = [...crawlRuns].sort(
        (a, b) =>
            new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    );

    return (
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Sources", href: "/sources" },
                    { label: "Crawl Runs", href: "/crawls" },
                ]}
            />
            <Box className="flex flex-wrap items-end justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        Crawl Runs
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 max-w-3xl text-sm text-muted-foreground"
                    >
                        Track crawl jobs across Sources. Crawling and discovery
                        are separate manual steps; open a run to start or review
                        discovery for that timestamped cache.
                    </MuiTypography>
                </Box>
                <Button asChild>
                    <Link href="/crawls/new">Start crawl</Link>
                </Button>
            </Box>
            <ResizableTable<CrawlRun>
                ariaLabel="Crawl runs"
                rowKey="id"
                dataSource={rows}
                pagination={{ defaultPageSize: 20, showSizeChanger: true }}
                columns={[
                    {
                        title: "Run",
                        dataIndex: "id",
                        key: "id",
                        width: 165,
                        sorter: {
                            compare: (a, b) => a.id.localeCompare(b.id),
                            multiple: 6,
                        },
                        render: (value, run) => (
                            <Link
                                href={`/crawls/${run.id}`}
                                className="font-mono text-xs font-medium hover:underline"
                            >
                                {value}
                            </Link>
                        ),
                    },
                    {
                        title: "Source",
                        dataIndex: "sourceName",
                        key: "source",
                        width: 190,
                        filterSearch: true,
                        filters: [
                            ...new Set(rows.map((r) => r.sourceName)),
                        ].map((v) => ({ text: v, value: v })),
                        onFilter: (v, r) => r.sourceName === v,
                        sorter: {
                            compare: (a, b) =>
                                a.sourceName.localeCompare(b.sourceName),
                            multiple: 5,
                        },
                        render: (value, run) => (
                            <Link
                                href={`/sources/${run.sourceId}`}
                                className="font-medium hover:underline"
                            >
                                {value}
                            </Link>
                        ),
                    },
                    {
                        title: "Strategy",
                        dataIndex: "strategyName",
                        key: "strategy",
                        width: 150,
                        filters: [
                            ...new Set(rows.map((r) => r.strategyName)),
                        ].map((v) => ({ text: v, value: v })),
                        onFilter: (v, r) => r.strategyName === v,
                        sorter: {
                            compare: (a, b) =>
                                a.strategyName.localeCompare(b.strategyName),
                            multiple: 4,
                        },
                    },
                    {
                        title: "Crawl",
                        dataIndex: "status",
                        key: "status",
                        width: 105,
                        filters: [
                            "queued",
                            "running",
                            "succeeded",
                            "failed",
                        ].map((v) => ({ text: v, value: v })),
                        onFilter: (v, r) => r.status === v,
                        sorter: {
                            compare: (a, b) => a.status.localeCompare(b.status),
                            multiple: 3,
                        },
                        render: (value) => <RunStatus status={value} />,
                    },
                    {
                        title: "Discovery",
                        dataIndex: "discoveryStatus",
                        key: "discoveryStatus",
                        width: 120,
                        filters: [
                            "not_started",
                            "queued",
                            "running",
                            "succeeded",
                            "failed",
                        ].map((v) => ({ text: v.replace("_", " "), value: v })),
                        onFilter: (v, r) => r.discoveryStatus === v,
                        sorter: {
                            compare: (a, b) =>
                                a.discoveryStatus.localeCompare(
                                    b.discoveryStatus,
                                ),
                            multiple: 2,
                        },
                        render: (value) => <DiscoveryStatus status={value} />,
                    },
                    {
                        title: "Progress",
                        dataIndex: "progressPercent",
                        key: "progress",
                        width: 95,
                        hidden: true,
                        sorter: {
                            compare: (a, b) =>
                                a.progressPercent - b.progressPercent,
                            multiple: 1,
                        },
                        render: (v) => `${v}%`,
                    },
                    {
                        title: "Pages",
                        dataIndex: "pagesCrawled",
                        key: "pages",
                        width: 80,
                        sorter: {
                            compare: (a, b) => a.pagesCrawled - b.pagesCrawled,
                            multiple: 1,
                        },
                    },
                    {
                        title: "Started",
                        dataIndex: "startedAt",
                        key: "started",
                        width: 160,
                        defaultSortOrder: "descend",
                        sorter: {
                            compare: (a, b) =>
                                new Date(a.startedAt).getTime() -
                                new Date(b.startedAt).getTime(),
                            multiple: 7,
                        },
                        render: (v) => new Date(v).toLocaleString(),
                    },
                    {
                        title: "Cache",
                        dataIndex: "cacheTimestamp",
                        key: "cache",
                        width: 145,
                        hidden: true,
                        render: (v) => (v ? new Date(v).toLocaleString() : "—"),
                    },
                ]}
            />
        </Box>
    );
}
