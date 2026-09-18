import ResizableTable from "@/components/ui/resizable-table";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/use-toast";
import {
    benchmarkRuns,
    benchmarkStrategies,
    extractStrategies,
    publishStrategies,
    sourceStrategyAssignments,
    sources,
    transformStrategies,
} from "@/mock-control-plane";
import { Plus } from "lucide-react";

function optionName(options: { id: string; name: string }[], id: string) {
    return options.find((option) => option.id === id)?.name ?? id;
}

export default function BenchmarkStrategies() {
    const { toast } = useToast();
    // TODO(strategy-api): GET global immutable ETL strategy definitions and available extractor/transform/publish-ready choices.
    // TODO(strategy-db): Persist strategy definitions independently of Sources.
    // TODO(benchmark-db): Load latest benchmark summaries by strategy across Sources.
    // TODO(source-strategy-db): Load admin-approved Source ↔ Strategy assignments used by Publishing.

    function createStrategy() {
        toast({
            title: "Strategy editor not connected",
            description:
                "Would create a global ETL strategy independent of any Source.",
        });
    }

    const rows = benchmarkStrategies.map((strategy) => {
        const assignments = sourceStrategyAssignments.filter(
            (item) => item.strategyId === strategy.id,
        );
        const latestRun = benchmarkRuns.find(
            (run) => run.strategyId === strategy.id,
        );
        return { ...strategy, assignments, latestRun };
    });

    return (
        <div className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Strategies", href: "/benchmarks/strategies" },
                ]}
            />
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold">Strategies</h1>
                    <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                        Strategies are reusable Extract → Transform →
                        Publish-ready definitions. They do not belong to a
                        Source. Benchmark Runs test them against the Promoted
                        Golden Samples for a Source.
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <Button variant="outline" onClick={createStrategy}>
                        <Plus className="mr-2 h-4 w-4" />
                        New strategy
                    </Button>
                </div>
            </div>

            <section
                aria-labelledby="strategies-table-heading"
                className="space-y-3"
            >
                <div>
                    <h2
                        id="strategies-table-heading"
                        className="text-base font-semibold"
                    >
                        Strategies
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Admins can promote/link a proven strategy to a Source
                        from a completed Benchmark Report. That link is what
                        makes it selectable in Publishing.
                    </p>
                </div>
                <ResizableTable
                    ariaLabel="Strategies"
                    rowKey="id"
                    size="middle"
                    dataSource={rows}
                    pagination={{ defaultPageSize: 20, showSizeChanger: true }}
                    columns={[
                        {
                            title: "Strategy",
                            key: "name",
                            sorter: {
                                compare: (a, b) => a.name.localeCompare(b.name),
                                multiple: 6,
                            },
                            render: (_, row) => (
                                <div>
                                    <div className="font-medium">
                                        {row.name}
                                    </div>
                                    <div className="mt-0.5 text-xs text-muted-foreground">
                                        {row.description}
                                    </div>
                                </div>
                            ),
                        },
                        {
                            title: "Extract",
                            key: "extract",
                            sorter: {
                                compare: (a, b) =>
                                    optionName(
                                        extractStrategies,
                                        a.extractOptionId,
                                    ).localeCompare(
                                        optionName(
                                            extractStrategies,
                                            b.extractOptionId,
                                        ),
                                    ),
                                multiple: 5,
                            },
                            render: (_, row) =>
                                optionName(
                                    extractStrategies,
                                    row.extractOptionId,
                                ),
                        },
                        {
                            title: "Transform",
                            key: "transform",
                            sorter: {
                                compare: (a, b) =>
                                    optionName(
                                        transformStrategies,
                                        a.transformOptionId,
                                    ).localeCompare(
                                        optionName(
                                            transformStrategies,
                                            b.transformOptionId,
                                        ),
                                    ),
                                multiple: 4,
                            },
                            render: (_, row) =>
                                optionName(
                                    transformStrategies,
                                    row.transformOptionId,
                                ),
                        },
                        {
                            title: "Publish-ready",
                            key: "publish",
                            sorter: {
                                compare: (a, b) =>
                                    optionName(
                                        publishStrategies,
                                        a.publishReadyOptionId,
                                    ).localeCompare(
                                        optionName(
                                            publishStrategies,
                                            b.publishReadyOptionId,
                                        ),
                                    ),
                                multiple: 3,
                            },
                            render: (_, row) =>
                                optionName(
                                    publishStrategies,
                                    row.publishReadyOptionId,
                                ),
                        },
                        {
                            title: "Status",
                            dataIndex: "status",
                            key: "status",
                            width: 120,
                            filters: ["draft", "active", "archived"].map(
                                (value) => ({ text: value, value }),
                            ),
                            onFilter: (value, row) => row.status === value,
                            sorter: {
                                compare: (a, b) =>
                                    a.status.localeCompare(b.status),
                                multiple: 2,
                            },
                            render: (value) => (
                                <Badge
                                    variant={
                                        value === "active"
                                            ? "default"
                                            : "secondary"
                                    }
                                    className="capitalize"
                                >
                                    {value}
                                </Badge>
                            ),
                        },
                        {
                            title: "Linked Sources",
                            key: "linked",
                            width: 180,
                            sorter: {
                                compare: (a, b) =>
                                    a.assignments.length - b.assignments.length,
                                multiple: 1,
                            },
                            render: (_, row) =>
                                row.assignments.length ? (
                                    <div className="flex flex-wrap gap-1">
                                        {row.assignments.map((assignment) => (
                                            <Badge
                                                key={assignment.sourceId}
                                                variant="outline"
                                            >
                                                {sources.find(
                                                    (source) =>
                                                        source.id ===
                                                        assignment.sourceId,
                                                )?.name ?? assignment.sourceId}
                                            </Badge>
                                        ))}
                                    </div>
                                ) : (
                                    <span className="text-sm text-muted-foreground">
                                        None
                                    </span>
                                ),
                        },
                    ]}
                />
            </section>
        </div>
    );
}
