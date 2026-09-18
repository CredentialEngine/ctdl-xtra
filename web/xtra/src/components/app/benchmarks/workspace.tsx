import ResizableTable from "@/components/ui/resizable-table";
import type { DiscoveredPageLabel } from "@/domain";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
    getEffectiveCrawlRunId,
    getEffectiveDiscoveredPages,
    goldenSamples,
    sources,
} from "@/mock-control-plane";
import { useState, type Key } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function BenchmarkWorkspace() {
    const { sourceId } = useParams<{ sourceId: string }>();
    const [labelFilter, setLabelFilter] = useState<Key[] | null>(null);
    const [goldenFilter, setGoldenFilter] = useState<Key[] | null>(null);
    // TODO(source-db): GET the Source and its discovered-page inventory from PostgreSQL.
    // TODO(benchmark-db): GET the Source Promoted Golden Sample Set and Source-scoped benchmark history.
    const source = sources.find((item) => item.id === sourceId);
    if (!source) return <div>Benchmark workspace not found.</div>;

    const effectiveCrawlRunId = getEffectiveCrawlRunId(sourceId);
    const pages = getEffectiveDiscoveredPages(sourceId).filter(
        (page) =>
            !page.labels.includes("Ignore") &&
            !page.labels.includes("Unclassified"),
    );
    const golden = goldenSamples.filter(
        (sample) => sample.sourceId === sourceId,
    );
    const availableLabels = [...new Set(pages.flatMap((page) => page.labels))];
    const promotedCount =
        pages.filter((page) => page.isGolden).length ||
        golden.length ||
        source.goldenSamples;
    const candidateCount = pages.filter((page) => !page.isGolden).length;

    return (
        <div className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Workspaces", href: "/benchmarks/workspaces" },
                    {
                        label: source.name,
                        href: `/benchmarks/workspaces/${source.id}`,
                    },
                ]}
            />

            <div>
                <h1 className="text-2xl font-semibold">{source.name}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    {source.url}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                    Using discovered pages from crawl cache:{" "}
                    {effectiveCrawlRunId ?? "none"}
                </p>
            </div>

            <div
                className="grid gap-3 sm:grid-cols-3"
                aria-label="Discovered page quick filters"
            >
                <Card
                    className={
                        goldenFilter === null ? "ring-2 ring-primary/30" : ""
                    }
                >
                    <button
                        type="button"
                        className="block w-full text-left"
                        aria-pressed={goldenFilter === null}
                        onClick={() => setGoldenFilter(null)}
                    >
                        <CardContent className="p-4">
                            <div className="text-xs text-muted-foreground">
                                All discovered pages
                            </div>
                            <div className="mt-1 text-2xl font-semibold">
                                {pages.length}
                            </div>
                        </CardContent>
                    </button>
                </Card>
                <Card
                    className={
                        goldenFilter?.includes("golden")
                            ? "ring-2 ring-primary/30"
                            : ""
                    }
                >
                    <button
                        type="button"
                        className="block w-full text-left"
                        aria-pressed={Boolean(goldenFilter?.includes("golden"))}
                        onClick={() => setGoldenFilter(["golden"])}
                    >
                        <CardContent className="p-4">
                            <div className="text-xs text-muted-foreground">
                                Promoted Golden
                            </div>
                            <div className="mt-1 text-2xl font-semibold">
                                {promotedCount}
                            </div>
                        </CardContent>
                    </button>
                </Card>
                <Card
                    className={
                        goldenFilter?.includes("candidate")
                            ? "ring-2 ring-primary/30"
                            : ""
                    }
                >
                    <button
                        type="button"
                        className="block w-full text-left"
                        aria-pressed={Boolean(
                            goldenFilter?.includes("candidate"),
                        )}
                        onClick={() => setGoldenFilter(["candidate"])}
                    >
                        <CardContent className="p-4">
                            <div className="text-xs text-muted-foreground">
                                Candidates
                            </div>
                            <div className="mt-1 text-2xl font-semibold">
                                {candidateCount}
                            </div>
                        </CardContent>
                    </button>
                </Card>
            </div>

            <div className="flex justify-end">
                <Button variant="outline" asChild>
                    <Link href={`/benchmarks/workspaces/${source.id}/golden`}>
                        View Promoted Golden Samples
                    </Link>
                </Button>
            </div>

            <section
                aria-labelledby="discovered-pages-heading"
                className="space-y-3"
            >
                <div>
                    <h2
                        id="discovered-pages-heading"
                        className="text-base font-semibold"
                    >
                        Discovered pages
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Run ETL with an existing Strategy on any page, then
                        audit the generated stage outputs before promoting it to
                        the Golden Sample Set.
                    </p>
                </div>
                <ResizableTable
                    ariaLabel="Discovered pages"
                    rowKey="id"
                    size="middle"
                    dataSource={pages}
                    pagination={{ defaultPageSize: 25, showSizeChanger: true }}
                    onChange={(_, filters) => {
                        setLabelFilter(
                            (filters.labels as Key[] | null) ?? null,
                        );
                        setGoldenFilter(
                            (filters.golden as Key[] | null) ?? null,
                        );
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
                                    <div className="max-w-[720px] truncate text-xs text-muted-foreground">
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
                            filters: availableLabels.map((value) => ({
                                text: value,
                                value,
                            })),
                            filteredValue: labelFilter,
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
                            render: (values) => (
                                <div className="flex flex-wrap gap-1">
                                    {values.map((value: string) => (
                                        <Badge key={value} variant="outline">
                                            {value}
                                        </Badge>
                                    ))}
                                </div>
                            ),
                        },
                        {
                            title: "Promoted Golden",
                            dataIndex: "isGolden",
                            key: "golden",
                            width: 130,
                            filteredValue: goldenFilter,
                            filters: [
                                { text: "Promoted", value: "golden" },
                                { text: "Candidate", value: "candidate" },
                            ],
                            onFilter: (value, page) =>
                                (page.isGolden ? "golden" : "candidate") ===
                                value,
                            sorter: {
                                compare: (a, b) =>
                                    Number(a.isGolden) - Number(b.isGolden),
                                multiple: 2,
                            },
                            render: (value) =>
                                value ? (
                                    <Badge>Promoted</Badge>
                                ) : (
                                    <Badge variant="secondary">Candidate</Badge>
                                ),
                        },
                        {
                            title: "Actions",
                            key: "actions",
                            width: 170,
                            render: (_, page) => (
                                <div className="flex gap-2">
                                    <Button size="sm" variant="outline" asChild>
                                        <Link
                                            href={`/benchmarks/workspaces/${source.id}/pages/${page.id}`}
                                        >
                                            Audit
                                        </Link>
                                    </Button>
                                    <Button size="sm" asChild>
                                        <Link
                                            href={`/benchmarks/workspaces/${source.id}/pages/${page.id}/run`}
                                        >
                                            Run
                                        </Link>
                                    </Button>
                                </div>
                            ),
                        },
                    ]}
                />
            </section>
        </div>
    );
}
