import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import { Box, Checkbox, ListItemText, MenuItem, Select } from "@mui/material";
import { useMemo, useState } from "react";
import Link from "@/components/ui/route-link";
import { useParams } from "next/navigation";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import ResizableTable from "@/components/ui/resizable-table";
import { useSnackbar } from "@/components/ui/snackbar-provider";
import { crawlRuns, discoveredPages } from "@/mock-control-plane";
import type {
    DiscoveredPage,
    DiscoveredPageLabel,
    DiscoverStatus,
} from "@/domain";

const labelOptions: DiscoveredPageLabel[] = [
    "Course",
    "Learning Opportunity",
    "Competency",
    "Credential",
    "Organization",
    "Ignore",
    "Unclassified",
];

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

export default function CrawlDiscovery() {
    const { runId } = useParams<{ runId: string }>();
    const { showSnackbar } = useSnackbar();
    const run = crawlRuns.find((item) => item.id === runId);
    const [status, setStatus] = useState<DiscoverStatus>(
        run?.discoveryStatus ?? "not_started",
    );
    const [pages, setPages] = useState<DiscoveredPage[]>(() =>
        discoveredPages.filter((page) => page.crawlRunId === runId),
    );

    const interesting = useMemo(
        () =>
            pages.filter(
                (page) =>
                    !page.labels.includes("Ignore") &&
                    !page.labels.includes("Unclassified"),
            ),
        [pages],
    );
    const ignored = useMemo(
        () => pages.filter((page) => page.labels.includes("Ignore")),
        [pages],
    );
    const unclassified = useMemo(
        () =>
            pages.filter(
                (page) =>
                    page.labels.includes("Unclassified") ||
                    page.labels.length === 0,
            ),
        [pages],
    );

    // TODO(discovery-db): Load the cached-page inventory and persisted multi-label classifications for this exact crawlRunId.
    // TODO(blob-store): Enumerate the downloaded cached page artifacts for the crawl run so every cached page can be reviewed/classified.
    if (!run) return <Box>Crawl run not found.</Box>;
    const currentRun = run;

    function runDiscovery() {
        if (currentRun.status !== "succeeded") return;
        // TODO(discovery-api): Create/re-run discovery for this crawlRunId using the crawl cache at run.cachePath. This is a separate post-crawl workflow.
        // TODO(argo-events): Persist queued/running/completed/failed discovery workflow events and counters for this crawl run.
        // TODO(discovery-db): Upsert the discovered-page rows and their labels against crawlRunId; keep prior manual overrides according to backend policy.
        setStatus("running");
        showSnackbar({
            title: "Discovery queued",
            description: "Classification will run against this crawl cache.",
        });
    }

    function updateLabels(pageId: string, values: string[]) {
        const next = (
            values.length ? values : ["Unclassified"]
        ) as DiscoveredPageLabel[];
        // TODO(discovery-db): Persist this manual label override for { crawlRunId, pageId }, including who changed it and when.
        setPages((current) =>
            current.map((page) =>
                page.id === pageId ? { ...page, labels: next } : page,
            ),
        );
    }

    return (
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Sources", href: "/sources" },
                    { label: run.sourceName, href: `/sources/${run.sourceId}` },
                    {
                        label: run.cacheTimestamp
                            ? new Date(run.cacheTimestamp).toLocaleString()
                            : run.id,
                        href: `/crawls/${run.id}`,
                    },
                    { label: "Discovery", href: `/crawls/${run.id}/discovery` },
                ]}
            />

            <Box className="flex flex-wrap items-start justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        Discovery
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        {run.sourceName} · cache{" "}
                        {run.cacheTimestamp
                            ? new Date(run.cacheTimestamp).toLocaleString()
                            : "not available"}
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-2 max-w-2xl text-sm text-muted-foreground"
                    >
                        This is a separate manual phase for this crawl only.
                        Nothing starts until you choose Run discovery.
                    </MuiTypography>
                </Box>
                <Box className="flex items-center gap-2">
                    <DiscoveryStatus status={status} />
                    <Button
                        onClick={runDiscovery}
                        disabled={
                            run.status !== "succeeded" || status === "running"
                        }
                    >
                        {status === "succeeded"
                            ? "Run discovery again"
                            : "Run discovery"}
                    </Button>
                </Box>
            </Box>

            <Box className="grid gap-3 sm:grid-cols-3">
                <Box className="rounded-lg bg-muted/40 p-4">
                    <Box className="text-xs text-muted-foreground">
                        Interesting pages
                    </Box>
                    <Box className="mt-1 text-2xl font-semibold">
                        {interesting.length}
                    </Box>
                </Box>
                <Box className="rounded-lg bg-muted/40 p-4">
                    <Box className="text-xs text-muted-foreground">
                        Unclassified
                    </Box>
                    <Box className="mt-1 text-2xl font-semibold">
                        {unclassified.length}
                    </Box>
                </Box>
                <Box className="rounded-lg bg-muted/40 p-4">
                    <Box className="text-xs text-muted-foreground">Ignored</Box>
                    <Box className="mt-1 text-2xl font-semibold">
                        {ignored.length}
                    </Box>
                </Box>
            </Box>

            <MuiBox
                component="section"
                aria-labelledby="cached-pages-heading"
                className="space-y-3"
            >
                <Box>
                    <MuiTypography
                        variant="h2"
                        component="h2"
                        id="cached-pages-heading"
                        className="text-base font-semibold"
                    >
                        Cached pages
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        Review the pages downloaded by this crawl and correct
                        labels manually when automated discovery misses or
                        misclassifies a page.
                    </MuiTypography>
                </Box>
                <ResizableTable<DiscoveredPage>
                    ariaLabel="Cached page discovery classifications"
                    rowKey="id"
                    size="middle"
                    dataSource={pages}
                    pagination={{ defaultPageSize: 25, showSizeChanger: true }}
                    locale={{
                        emptyText:
                            "The cached page inventory will appear here after the crawl cache is indexed.",
                    }}
                    columns={[
                        {
                            title: "Page",
                            key: "page",
                            sorter: {
                                compare: (a, b) =>
                                    a.title.localeCompare(b.title),
                                multiple: 4,
                            },
                            render: (_, page) => (
                                <Box>
                                    <Box className="font-medium">
                                        {page.title}
                                    </Box>
                                    <a
                                        className="block max-w-[720px] truncate text-xs text-muted-foreground hover:underline"
                                        href={page.url}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {page.url}
                                    </a>
                                </Box>
                            ),
                        },
                        {
                            title: "Labels",
                            dataIndex: "labels",
                            key: "labels",
                            width: 340,
                            filters: labelOptions.map((value) => ({
                                text: value,
                                value,
                            })),
                            filterSearch: true,
                            onFilter: (value, page) =>
                                page.labels.includes(
                                    String(value) as DiscoveredPageLabel,
                                ),
                            sorter: {
                                compare: (a, b) =>
                                    a.labels
                                        .join(", ")
                                        .localeCompare(b.labels.join(", ")),
                                multiple: 3,
                            },
                            render: (values: DiscoveredPageLabel[], page) => (
                                <Select<DiscoveredPageLabel[]>
                                    multiple
                                    size="small"
                                    fullWidth
                                    value={values}
                                    inputProps={{
                                        "aria-label": `Labels for ${page.title}`,
                                    }}
                                    onChange={(event) => {
                                        const next = event.target.value;
                                        updateLabels(
                                            page.id,
                                            typeof next === "string"
                                                ? next.split(",")
                                                : next,
                                        );
                                    }}
                                    renderValue={(selected) =>
                                        selected.join(", ")
                                    }
                                    MenuProps={{
                                        disableScrollLock: true,
                                    }}
                                >
                                    {labelOptions.map((value) => (
                                        <MenuItem key={value} value={value}>
                                            <Checkbox
                                                checked={values.includes(value)}
                                            />
                                            <ListItemText primary={value} />
                                        </MenuItem>
                                    ))}
                                </Select>
                            ),
                        },
                        {
                            title: "Confidence",
                            dataIndex: "confidence",
                            key: "confidence",
                            width: 120,
                            sorter: {
                                compare: (a, b) =>
                                    (a.confidence ?? 0) - (b.confidence ?? 0),
                                multiple: 2,
                            },
                            render: (value) =>
                                value == null
                                    ? "—"
                                    : `${Math.round(value * 100)}%`,
                        },
                    ]}
                />
            </MuiBox>

            <Box className="flex justify-end">
                <Button variant="outline" asChild>
                    <Link href={`/crawls/${run.id}`}>Back to crawl run</Link>
                </Button>
            </Box>
        </Box>
    );
}
