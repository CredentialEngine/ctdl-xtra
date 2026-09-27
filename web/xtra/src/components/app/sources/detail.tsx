import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
import type { TableColumnsType } from "antd";
import ExternalLink from "@mui/icons-material/OpenInNew";
import Trash2 from "@mui/icons-material/Delete";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { useState } from "react";
import Link from "@/components/ui/route-link";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import ResizableTable from "@/components/ui/resizable-table";
import { useSnackbar } from "@/components/ui/snackbar-provider";
import { crawlRuns as crawlRunFixtures, sources } from "@/mock-control-plane";
import type { CrawlRun, DiscoverStatus } from "@/domain";

function CrawlRunStatus({ status }: { status: CrawlRun["status"] }) {
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

function DiscoveryStatus({ status }: { status: DiscoverStatus }) {
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

function formatDuration(seconds?: number) {
    if (seconds == null) return "—";
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ${seconds % 60}s`;
}

export default function SourceDetail() {
    const { sourceId } = useParams<{ sourceId: string }>();
    const { showSnackbar } = useSnackbar();
    const source = sources.find((item) => item.id === sourceId);
    const [crawlRuns, setCrawlRuns] = useState<CrawlRun[]>(() =>
        crawlRunFixtures.filter((run) => run.sourceId === sourceId),
    );
    const [lkgRunId, setLkgRunId] = useState(source?.lkgCrawlRunId);

    // TODO(source-db): GET Source metadata including latest successful crawl id and selected LKG crawl/cache id from PostgreSQL.
    // TODO(crawl-db): GET all crawl runs for this Source, including strategy snapshots, crawl progress, discovery progress, cache paths, timestamps, errors, and metrics.
    // TODO(argo-events): Argo callbacks update crawl/discovery run state through the API; active pages should refresh from persisted DB state.
    if (!source) return <Box>Source not found.</Box>;

    function setLkg(run: CrawlRun) {
        if (run.status !== "succeeded" || !run.cacheTimestamp) return;
        // TODO(source-db): PATCH the Source lkgCrawlRunId / effective cache timestamp in PostgreSQL.
        setLkgRunId(run.id);
        showSnackbar({
            title: "LKG cache selected",
            description: new Date(run.cacheTimestamp).toLocaleString(),
        });
    }

    function deleteCrawl(run: CrawlRun) {
        if (run.status === "running" || run.status === "queued") {
            showSnackbar({ title: "Active crawls cannot be deleted" });
            return;
        }
        if (run.id === lkgRunId) {
            showSnackbar({
                title: "LKG crawl cannot be deleted",
                description: "Choose another LKG cache first.",
            });
            return;
        }
        if (!window.confirm(`Delete crawl ${run.id} and its cached artifacts?`))
            return;
        // TODO(blob-store): Delete the timestamped crawl cache folder only after backend retention checks allow it.
        // TODO(discovery-db): Delete/retain discovery classifications according to audit-retention policy when their crawl cache is removed.
        // TODO(crawl-db): Delete or soft-delete the crawl run row in PostgreSQL according to audit-retention policy.
        setCrawlRuns((runs) => runs.filter((item) => item.id !== run.id));
    }

    return (
        <Box className="space-y-7">
            <BreadcrumbTrail
                items={[
                    { label: "Sources", href: "/sources" },
                    { label: source.name, href: `/sources/${source.id}` },
                ]}
            />

            <Box className="flex flex-wrap items-start justify-between gap-4">
                <Box>
                    <Box className="flex flex-wrap items-center gap-2">
                        <MuiTypography
                            variant="h1"
                            component="h1"
                            className="text-2xl font-semibold"
                        >
                            {source.name}
                        </MuiTypography>
                        <Badge variant="outline">
                            {source.organizationName}
                        </Badge>
                        {source.tags.map((tag) => (
                            <Badge key={tag} variant="secondary">
                                {tag}
                            </Badge>
                        ))}
                    </Box>
                    <a
                        className="mt-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                    >
                        {source.url}
                        <ExternalLink className="h-3.5 w-3.5" />
                    </a>
                </Box>
                <Box className="flex gap-2">
                    <Button variant="outline" asChild>
                        <Link href={`/sources/${source.id}/edit`}>
                            Edit source
                        </Link>
                    </Button>
                </Box>
            </Box>

            <MuiBox
                component="section"
                aria-labelledby="source-crawl-runs-heading"
                className="space-y-3"
            >
                <Box className="flex flex-wrap items-end justify-between gap-3">
                    <Box>
                        <MuiTypography
                            variant="h2"
                            component="h2"
                            id="source-crawl-runs-heading"
                            className="text-base font-semibold"
                        >
                            Crawl runs
                        </MuiTypography>
                        <MuiTypography
                            component="p"
                            className="mt-1 text-sm text-muted-foreground"
                        >
                            Start crawls when you need them. Each successful run
                            keeps its own timestamped cache; discovery is a
                            separate manual step for that run.
                        </MuiTypography>
                    </Box>
                    <Button asChild>
                        <Link href={`/crawls/new?sourceId=${source.id}`}>
                            Start another crawl
                        </Link>
                    </Button>
                </Box>
                <ResizableTable<CrawlRun>
                    ariaLabel="Crawl runs for this Source"
                    rowKey="id"
                    size="middle"
                    dataSource={[...crawlRuns].sort(
                        (a, b) =>
                            new Date(b.startedAt).getTime() -
                            new Date(a.startedAt).getTime(),
                    )}
                    locale={{ emptyText: "No crawl runs for this Source." }}
                    pagination={{ defaultPageSize: 10, showSizeChanger: true }}
                    columns={
                        [
                            {
                                title: "Run",
                                dataIndex: "id",
                                key: "id",
                                width: 150,
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
                                title: "Strategy",
                                dataIndex: "strategyName",
                                key: "strategy",
                                width: 130,
                                filters: [
                                    ...new Set(
                                        crawlRuns.map(
                                            (run) => run.strategyName,
                                        ),
                                    ),
                                ].map((value) => ({ text: value, value })),
                                onFilter: (value, record) =>
                                    record.strategyName === value,
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
                                ].map((value) => ({ text: value, value })),
                                onFilter: (value, record) =>
                                    record.status === value,
                                render: (value) => (
                                    <CrawlRunStatus status={value} />
                                ),
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
                                ].map((value) => ({
                                    text: value.replace("_", " "),
                                    value,
                                })),
                                onFilter: (value, record) =>
                                    record.discoveryStatus === value,
                                render: (value) => (
                                    <DiscoveryStatus status={value} />
                                ),
                            },
                            {
                                title: "Interesting",
                                dataIndex: "interestingPages",
                                key: "interestingPages",
                                width: 100,
                                sorter: {
                                    compare: (a, b) =>
                                        (a.interestingPages ?? -1) -
                                        (b.interestingPages ?? -1),
                                    multiple: 2,
                                },
                                render: (value) => value ?? "—",
                            },
                            {
                                title: "Cache timestamp",
                                dataIndex: "cacheTimestamp",
                                key: "cacheTimestamp",
                                width: 165,
                                sorter: {
                                    compare: (a, b) =>
                                        new Date(
                                            a.cacheTimestamp ?? 0,
                                        ).getTime() -
                                        new Date(
                                            b.cacheTimestamp ?? 0,
                                        ).getTime(),
                                    multiple: 5,
                                },
                                render: (value) =>
                                    value
                                        ? new Date(value).toLocaleString()
                                        : "—",
                            },
                            {
                                title: "Pages",
                                dataIndex: "pagesCrawled",
                                key: "pagesCrawled",
                                width: 72,
                                sorter: {
                                    compare: (a, b) =>
                                        a.pagesCrawled - b.pagesCrawled,
                                    multiple: 3,
                                },
                            },
                            {
                                title: "Duration",
                                dataIndex: "durationSeconds",
                                key: "duration",
                                width: 86,
                                hidden: true,
                                render: formatDuration,
                            },
                            {
                                title: "Blob path",
                                dataIndex: "cachePath",
                                key: "cachePath",
                                hidden: true,
                                ellipsis: true,
                                render: (value) => value ?? "—",
                            },
                            {
                                title: "LKG",
                                key: "lkg",
                                width: 85,
                                filters: [
                                    { text: "LKG", value: true },
                                    { text: "Not LKG", value: false },
                                ],
                                onFilter: (value, record) =>
                                    (record.id === lkgRunId) === value,
                                render: (_, run) =>
                                    run.id === lkgRunId ? (
                                        <Badge>LKG</Badge>
                                    ) : run.status === "succeeded" ? (
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            onClick={() => setLkg(run)}
                                        >
                                            Set LKG
                                        </Button>
                                    ) : (
                                        "—"
                                    ),
                            },
                            {
                                title: "Actions",
                                key: "review",
                                width: 210,
                                render: (_, run) => (
                                    <Box className="flex items-center gap-1">
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            asChild
                                        >
                                            <Link href={`/crawls/${run.id}`}>
                                                Open run
                                            </Link>
                                        </Button>
                                        {run.status === "succeeded" && (
                                            <Button
                                                size="sm"
                                                variant="ghost"
                                                asChild
                                            >
                                                <Link
                                                    href={`/crawls/${run.id}/discovery`}
                                                >
                                                    {run.discoveryStatus ===
                                                    "not_started"
                                                        ? "Discovery"
                                                        : "Review discovery"}
                                                </Link>
                                            </Button>
                                        )}
                                    </Box>
                                ),
                            },
                            {
                                title: "",
                                key: "actions",
                                width: 52,
                                render: (_, run) => (
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        aria-label={`Delete ${run.id}`}
                                        disabled={
                                            run.status === "running" ||
                                            run.status === "queued" ||
                                            run.id === lkgRunId
                                        }
                                        onClick={() => deleteCrawl(run)}
                                    >
                                        <Trash2 className="h-4 w-4" />
                                    </Button>
                                ),
                            },
                        ] as TableColumnsType<CrawlRun>
                    }
                />
            </MuiBox>
        </Box>
    );
}
