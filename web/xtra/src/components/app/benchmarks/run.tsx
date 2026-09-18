import ResizableTable from "@/components/ui/resizable-table";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { useToast } from "@/components/ui/use-toast";
import {
    benchmarkRuns,
    benchmarkStrategies,
    extractStrategies,
    goldenSamples,
    publishStrategies,
    sourceStrategyAssignments,
    transformStrategies,
} from "@/mock-control-plane";
import {
    CheckCircle2,
    Clock3,
    GitBranch,
    Rocket,
    TriangleAlert,
} from "lucide-react";
import { useState, type Key } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

function optionName(options: { id: string; name: string }[], id?: string) {
    return options.find((option) => option.id === id)?.name ?? id ?? "—";
}

export default function BenchmarkRun() {
    const { runId } = useParams<{ runId: string }>();
    const { toast } = useToast();
    const [resultFilter, setResultFilter] = useState<Key[] | null>(null);
    // TODO(benchmark-db): GET benchmark run summary, immutable strategy snapshot, aggregate scores, report metadata, and per-sample results by run id.
    const run = benchmarkRuns.find((item) => item.id === runId);
    if (!run) return <div>Benchmark run not found.</div>;
    const currentRun = run;
    const samples = goldenSamples.filter(
        (sample) => sample.sourceId === run.sourceId,
    );
    const strategy = benchmarkStrategies.find(
        (item) => item.id === run.strategyId,
    );
    const overallScore = run.samples
        ? Math.round((run.passed / run.samples) * 1000) / 10
        : 0;
    const isAssignedToSource = sourceStrategyAssignments.some(
        (assignment) =>
            assignment.sourceId === run.sourceId &&
            assignment.strategyId === run.strategyId,
    );
    const sampleResult = (sample: (typeof samples)[number]) =>
        sample.stages.every((stage) => stage.status === "passed")
            ? "passed"
            : "failed";
    const mockedPassed = samples.filter(
        (sample) => sampleResult(sample) === "passed",
    ).length;
    const mockedFailed = samples.filter(
        (sample) => sampleResult(sample) === "failed",
    ).length;

    function promoteStrategy() {
        // TODO(source-strategy-db): Create/update the admin-approved Source ↔ Strategy assignment for this exact strategy version.
        // TODO(publishing-api): Publishing reads this assignment to make the Strategy available for this Source.
        toast({
            title: "Strategy promotion endpoint not connected",
            description: `Would promote ${currentRun.strategyName} for ${currentRun.sourceName}.`,
        });
    }

    return (
        <div className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Runs", href: "/benchmarks/runs" },
                    { label: run.id, href: `/benchmarks/runs/${run.id}` },
                ]}
            />
            <div>
                <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-2xl font-semibold">Benchmark Report</h1>
                    <Badge
                        variant={
                            run.status === "failed"
                                ? "destructive"
                                : run.status === "completed"
                                  ? "default"
                                  : "secondary"
                        }
                        className="whitespace-nowrap capitalize"
                    >
                        {run.status}
                    </Badge>
                </div>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                    {run.id}
                </p>
            </div>

            <div className="grid gap-3 rounded-lg bg-muted/30 p-4 md:grid-cols-5">
                <div>
                    <div className="text-xs text-muted-foreground">Source</div>
                    <Link
                        href={`/benchmarks/workspaces/${run.sourceId}`}
                        className="font-semibold hover:underline"
                    >
                        {run.sourceName}
                    </Link>
                </div>
                <div>
                    <div className="text-xs text-muted-foreground">
                        Strategy
                    </div>
                    <div className="font-semibold">{run.strategyName}</div>
                </div>
                <div>
                    <div className="text-xs text-muted-foreground">Started</div>
                    <div className="text-sm">
                        {new Date(run.startedAt).toLocaleString()}
                    </div>
                </div>
                <div>
                    <div className="text-xs text-muted-foreground">
                        Duration
                    </div>
                    <div className="inline-flex items-center gap-1.5 text-sm">
                        <Clock3 className="h-4 w-4" aria-hidden="true" />
                        {run.durationSeconds
                            ? `${run.durationSeconds}s`
                            : "In progress"}
                    </div>
                </div>
                <div>
                    <div className="text-xs text-muted-foreground">
                        Score / stage pass
                    </div>
                    <div className="text-sm font-medium">
                        {run.status === "failed"
                            ? "—"
                            : `${overallScore}% / ${run.stagePassRate}%`}
                    </div>
                </div>
            </div>

            {run.status !== "failed" && (
                <div
                    className="grid gap-3 sm:grid-cols-3"
                    aria-label="Sample result quick filters"
                >
                    <Card
                        className={
                            resultFilter === null
                                ? "ring-2 ring-primary/30"
                                : ""
                        }
                    >
                        <button
                            type="button"
                            className="block w-full text-left"
                            aria-pressed={resultFilter === null}
                            onClick={() => setResultFilter(null)}
                        >
                            <CardContent className="p-4">
                                <div className="text-xs text-muted-foreground">
                                    All sample results
                                </div>
                                <div className="mt-1 text-2xl font-semibold">
                                    {samples.length}
                                </div>
                            </CardContent>
                        </button>
                    </Card>
                    <Card
                        className={
                            resultFilter?.includes("passed")
                                ? "ring-2 ring-primary/30"
                                : ""
                        }
                    >
                        <button
                            type="button"
                            className="block w-full text-left"
                            aria-pressed={Boolean(
                                resultFilter?.includes("passed"),
                            )}
                            onClick={() => setResultFilter(["passed"])}
                        >
                            <CardContent className="p-4">
                                <div className="text-xs text-muted-foreground">
                                    Passed
                                </div>
                                <div className="mt-1 text-2xl font-semibold">
                                    {mockedPassed}
                                </div>
                            </CardContent>
                        </button>
                    </Card>
                    <Card
                        className={
                            resultFilter?.includes("failed")
                                ? "ring-2 ring-primary/30"
                                : ""
                        }
                    >
                        <button
                            type="button"
                            className="block w-full text-left"
                            aria-pressed={Boolean(
                                resultFilter?.includes("failed"),
                            )}
                            onClick={() => setResultFilter(["failed"])}
                        >
                            <CardContent className="p-4">
                                <div className="text-xs text-muted-foreground">
                                    Failed
                                </div>
                                <div className="mt-1 text-2xl font-semibold">
                                    {mockedFailed}
                                </div>
                            </CardContent>
                        </button>
                    </Card>
                </div>
            )}

            <Card className="border-0 shadow-none">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2 text-base">
                        <GitBranch className="h-4 w-4" />
                        Strategy snapshot
                    </CardTitle>
                    <CardDescription>
                        The exact ETL choices used by this run are preserved
                        with the report.
                    </CardDescription>
                </CardHeader>
                <CardContent className="px-0">
                    <div className="grid gap-3 md:grid-cols-3">
                        <div className="rounded-md bg-muted/30 p-3">
                            <div className="text-xs text-muted-foreground">
                                Extract
                            </div>
                            <div className="mt-1 text-sm font-medium">
                                {optionName(
                                    extractStrategies,
                                    strategy?.extractOptionId,
                                )}
                            </div>
                        </div>
                        <div className="rounded-md bg-muted/30 p-3">
                            <div className="text-xs text-muted-foreground">
                                Transform
                            </div>
                            <div className="mt-1 text-sm font-medium">
                                {optionName(
                                    transformStrategies,
                                    strategy?.transformOptionId,
                                )}
                            </div>
                        </div>
                        <div className="rounded-md bg-muted/30 p-3">
                            <div className="text-xs text-muted-foreground">
                                Publish-ready
                            </div>
                            <div className="mt-1 text-sm font-medium">
                                {optionName(
                                    publishStrategies,
                                    strategy?.publishReadyOptionId,
                                )}
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {run.status === "failed" ? (
                <Card className="border-destructive/30">
                    <CardContent className="flex gap-3 p-5">
                        <TriangleAlert className="mt-0.5 h-5 w-5 text-destructive" />
                        <div>
                            <div className="font-medium">
                                Benchmark job failed before a complete report
                                was produced.
                            </div>
                            <div className="mt-1 text-sm text-muted-foreground">
                                Review the run diagnostics and partial results
                                when available.
                            </div>
                        </div>
                    </CardContent>
                </Card>
            ) : (
                <section
                    aria-labelledby="sample-results-heading"
                    className="space-y-3"
                >
                    <div>
                        <h2
                            id="sample-results-heading"
                            className="text-base font-semibold"
                        >
                            Promoted Golden Sample results
                        </h2>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Open a sample name to audit its generated Extract,
                            Transform, and Publish-ready artifacts against the
                            approved Golden outputs.
                        </p>
                    </div>
                    <ResizableTable
                        ariaLabel="Benchmark run sample results"
                        rowKey="id"
                        size="middle"
                        dataSource={samples}
                        pagination={{
                            defaultPageSize: 25,
                            showSizeChanger: true,
                        }}
                        columns={[
                            {
                                title: "Promoted Golden Sample",
                                key: "sample",
                                sorter: {
                                    compare: (a, b) =>
                                        a.pageTitle.localeCompare(b.pageTitle),
                                    multiple: 5,
                                },
                                render: (_, sample) => (
                                    <div>
                                        <Link
                                            href={`/benchmarks/runs/${run.id}/samples/${sample.id}`}
                                            className="font-medium hover:underline"
                                        >
                                            {sample.pageTitle}
                                        </Link>
                                        <div className="max-w-[600px] truncate text-xs text-muted-foreground">
                                            {sample.pageUrl}
                                        </div>
                                    </div>
                                ),
                            },
                            {
                                title: "Labels",
                                dataIndex: "labels",
                                key: "labels",
                                width: 240,
                                sorter: {
                                    compare: (a, b) =>
                                        a.labels
                                            .join(", ")
                                            .localeCompare(b.labels.join(", ")),
                                    multiple: 4,
                                },
                                render: (values) => (
                                    <div className="flex flex-wrap gap-1">
                                        {values.map((value: string) => (
                                            <Badge
                                                key={value}
                                                variant="outline"
                                            >
                                                {value}
                                            </Badge>
                                        ))}
                                    </div>
                                ),
                            },
                            {
                                title: "Result",
                                key: "result",
                                width: 110,
                                filteredValue: resultFilter,
                                filters: [
                                    { text: "Passed", value: "passed" },
                                    { text: "Failed", value: "failed" },
                                ],
                                onFilter: (value, sample) =>
                                    sampleResult(sample) === value,
                                sorter: {
                                    compare: (a, b) =>
                                        sampleResult(a).localeCompare(
                                            sampleResult(b),
                                        ),
                                    multiple: 3,
                                },
                                render: (_, sample) => (
                                    <Badge
                                        variant={
                                            sampleResult(sample) === "passed"
                                                ? "default"
                                                : "destructive"
                                        }
                                    >
                                        {sampleResult(sample)}
                                    </Badge>
                                ),
                            },
                            {
                                title: "Extract",
                                key: "extract",
                                width: 120,
                                render: (_, sample) => {
                                    const stage = sample.stages.find(
                                        (item) => item.stage === "extract",
                                    );
                                    return (
                                        <Badge
                                            variant={
                                                stage?.status === "passed"
                                                    ? "default"
                                                    : "destructive"
                                            }
                                        >
                                            {stage?.status ?? "—"}
                                        </Badge>
                                    );
                                },
                            },
                            {
                                title: "Transform",
                                key: "transform",
                                width: 120,
                                render: (_, sample) => {
                                    const stage = sample.stages.find(
                                        (item) => item.stage === "transform",
                                    );
                                    return (
                                        <Badge
                                            variant={
                                                stage?.status === "passed"
                                                    ? "default"
                                                    : "destructive"
                                            }
                                        >
                                            {stage?.status ?? "—"}
                                        </Badge>
                                    );
                                },
                            },
                            {
                                title: "Publish-ready",
                                key: "publish",
                                width: 140,
                                render: (_, sample) => {
                                    const stage = sample.stages.find(
                                        (item) =>
                                            item.stage === "publish-ready",
                                    );
                                    return (
                                        <Badge
                                            variant={
                                                stage?.status === "passed"
                                                    ? "default"
                                                    : "destructive"
                                            }
                                        >
                                            {stage?.status ?? "—"}
                                        </Badge>
                                    );
                                },
                            },
                        ]}
                        locale={{
                            emptyText:
                                "No sample result rows are mocked for this Source yet.",
                        }}
                    />
                </section>
            )}

            {run.status === "completed" && !isAssignedToSource && (
                <Card className="border-primary/30">
                    <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                        <div>
                            <div className="font-medium">
                                Promote this Strategy?
                            </div>
                            <div className="mt-1 text-sm text-muted-foreground">
                                After reviewing the benchmark score, report, and
                                failed sample audits, link this exact global ETL
                                Strategy to the Source so it becomes available
                                in Publishing.
                            </div>
                        </div>
                        <Button onClick={promoteStrategy}>
                            <Rocket className="mr-2 h-4 w-4" />
                            Promote Strategy
                        </Button>
                    </CardContent>
                </Card>
            )}

            {isAssignedToSource && (
                <div className="flex items-center gap-2 text-sm">
                    <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                    <span>
                        This Strategy is already promoted for this Source and is
                        available in Publishing.
                    </span>
                </div>
            )}
        </div>
    );
}
