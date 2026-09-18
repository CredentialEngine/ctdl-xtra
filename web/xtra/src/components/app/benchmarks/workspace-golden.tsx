import ResizableTable from "@/components/ui/resizable-table";
import type { DiscoveredPageLabel } from "@/domain";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { goldenSamples, sources } from "@/mock-control-plane";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function BenchmarkWorkspaceGolden() {
    const { sourceId } = useParams<{ sourceId: string }>();
    // TODO(source-db): GET Source metadata.
    // TODO(benchmark-db): GET the Source Promoted Golden Sample Set with promotion metadata and artifact references.
    const source = sources.find((item) => item.id === sourceId);
    if (!source) return <div>Benchmark workspace not found.</div>;
    const samples = goldenSamples.filter(
        (sample) => sample.sourceId === sourceId,
    );

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
                    {
                        label: "Promoted Golden Samples",
                        href: `/benchmarks/workspaces/${source.id}/golden`,
                    },
                ]}
            />
            <div>
                <h1 className="text-2xl font-semibold">{source.name}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    {source.url}
                </p>
            </div>

            <section
                aria-labelledby="golden-table-heading"
                className="space-y-3"
            >
                <div>
                    <h2
                        id="golden-table-heading"
                        className="text-base font-semibold"
                    >
                        {samples.length || source.goldenSamples} Promoted Golden
                        Samples
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Each sample preserves the reviewed source document and
                        approved Extract, Transform, and Publish-ready outputs.
                    </p>
                </div>
                <ResizableTable
                    ariaLabel="Promoted Golden Samples"
                    rowKey="id"
                    size="middle"
                    dataSource={samples}
                    pagination={{ defaultPageSize: 25, showSizeChanger: true }}
                    columns={[
                        {
                            title: "Sample",
                            key: "sample",
                            sorter: {
                                compare: (a, b) =>
                                    a.pageTitle.localeCompare(b.pageTitle),
                                multiple: 4,
                            },
                            render: (_, sample) => (
                                <div>
                                    <Link
                                        href={`/benchmarks/workspaces/${source.id}/pages/${sample.pageId}`}
                                        className="font-medium hover:underline"
                                    >
                                        {sample.pageTitle}
                                    </Link>
                                    <div className="max-w-[700px] truncate text-xs text-muted-foreground">
                                        {sample.pageUrl}
                                    </div>
                                </div>
                            ),
                        },
                        {
                            title: "Labels",
                            dataIndex: "labels",
                            key: "labels",
                            width: 250,
                            filters: [
                                ...new Set(
                                    samples.flatMap((sample) => sample.labels),
                                ),
                            ].map((value) => ({ text: value, value })),
                            onFilter: (value, sample) =>
                                sample.labels.includes(
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
                            title: "Artifacts",
                            key: "artifacts",
                            width: 290,
                            render: () => (
                                <span className="text-xs text-muted-foreground">
                                    Source → Extract → Transform → Publish-ready
                                </span>
                            ),
                        },
                        {
                            title: "Promoted",
                            dataIndex: "promotedAt",
                            key: "promoted",
                            width: 190,
                            sorter: {
                                compare: (a, b) =>
                                    new Date(a.promotedAt ?? 0).getTime() -
                                    new Date(b.promotedAt ?? 0).getTime(),
                                multiple: 2,
                            },
                            render: (value) =>
                                value ? new Date(value).toLocaleString() : "—",
                        },
                    ]}
                    locale={{
                        emptyText:
                            "No Promoted Golden Samples yet. Promote reviewed discovered pages from Discovered Pages.",
                    }}
                />
            </section>
        </div>
    );
}
