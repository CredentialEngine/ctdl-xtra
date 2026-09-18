import { Select as AntSelect } from "antd";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import ResizableTable from "@/components/ui/resizable-table";
import { useToast } from "@/components/ui/use-toast";
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
    const { toast } = useToast();
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
    if (!run) return <div>Crawl run not found.</div>;
    const currentRun = run;

    function runDiscovery() {
        if (currentRun.status !== "succeeded") return;
        // TODO(discovery-api): Create/re-run discovery for this crawlRunId using the crawl cache at run.cachePath. This is a separate post-crawl workflow.
        // TODO(argo-events): Persist queued/running/completed/failed discovery workflow events and counters for this crawl run.
        // TODO(discovery-db): Upsert the discovered-page rows and their labels against crawlRunId; keep prior manual overrides according to backend policy.
        setStatus("running");
        toast({
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
        <div className="space-y-6">
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

            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold">Discovery</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {run.sourceName} · cache{" "}
                        {run.cacheTimestamp
                            ? new Date(run.cacheTimestamp).toLocaleString()
                            : "not available"}
                    </p>
                    <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                        This is a separate manual phase for this crawl only.
                        Nothing starts until you choose Run discovery.
                    </p>
                </div>
                <div className="flex items-center gap-2">
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
                </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-muted/40 p-4">
                    <div className="text-xs text-muted-foreground">
                        Interesting pages
                    </div>
                    <div className="mt-1 text-2xl font-semibold">
                        {interesting.length}
                    </div>
                </div>
                <div className="rounded-lg bg-muted/40 p-4">
                    <div className="text-xs text-muted-foreground">
                        Unclassified
                    </div>
                    <div className="mt-1 text-2xl font-semibold">
                        {unclassified.length}
                    </div>
                </div>
                <div className="rounded-lg bg-muted/40 p-4">
                    <div className="text-xs text-muted-foreground">Ignored</div>
                    <div className="mt-1 text-2xl font-semibold">
                        {ignored.length}
                    </div>
                </div>
            </div>

            <section
                aria-labelledby="cached-pages-heading"
                className="space-y-3"
            >
                <div>
                    <h2
                        id="cached-pages-heading"
                        className="text-base font-semibold"
                    >
                        Cached pages
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Review the pages downloaded by this crawl and correct
                        labels manually when automated discovery misses or
                        misclassifies a page.
                    </p>
                </div>
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
                                <div>
                                    <div className="font-medium">
                                        {page.title}
                                    </div>
                                    <a
                                        className="block max-w-[720px] truncate text-xs text-muted-foreground hover:underline"
                                        href={page.url}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {page.url}
                                    </a>
                                </div>
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
                                <AntSelect
                                    aria-label={`Labels for ${page.title}`}
                                    mode="multiple"
                                    value={values}
                                    onChange={(next) =>
                                        updateLabels(page.id, next)
                                    }
                                    options={labelOptions.map((value) => ({
                                        label: value,
                                        value,
                                    }))}
                                    maxTagCount="responsive"
                                    style={{ width: "100%" }}
                                />
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
            </section>

            <div className="flex justify-end">
                <Button variant="outline" asChild>
                    <Link href={`/crawls/${run.id}`}>Back to crawl run</Link>
                </Button>
            </div>
        </div>
    );
}
