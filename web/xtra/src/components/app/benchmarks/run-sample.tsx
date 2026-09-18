import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { benchmarkRuns, goldenSamples } from "@/mock-control-plane";
import {
    ArrowDown,
    CheckCircle2,
    FileCode2,
    FileText,
    XCircle,
} from "lucide-react";
import { useParams } from "next/navigation";

export default function BenchmarkRunSample() {
    const { runId, sampleId } = useParams<{
        runId: string;
        sampleId: string;
    }>();
    // TODO(benchmark-db): GET this sample result with source document, generated artifact refs, Golden artifact refs, diffs, scores, logs, and timings.
    const run = benchmarkRuns.find((item) => item.id === runId);
    const sample = goldenSamples.find(
        (item) => item.id === sampleId && item.sourceId === run?.sourceId,
    );
    if (!run || !sample) return <div>Benchmark sample result not found.</div>;

    return (
        <div className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Runs", href: "/benchmarks/runs" },
                    { label: run.id, href: `/benchmarks/runs/${run.id}` },
                    {
                        label: sample.pageTitle,
                        href: `/benchmarks/runs/${run.id}/samples/${sample.id}`,
                    },
                ]}
            />
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold">Sample Audit</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {sample.pageTitle}
                    </p>
                </div>
            </div>

            <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
                <Card className="xl:sticky xl:top-24">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-base">
                            <FileText className="h-4 w-4" />
                            Source Document
                        </CardTitle>
                        <CardDescription>
                            The same approved source input represented by this
                            Golden Sample.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <pre className="max-h-[720px] overflow-auto rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap">{`SOURCE: ${sample.pageUrl}\n\n${sample.pageTitle}`}</pre>
                    </CardContent>
                </Card>

                <div className="space-y-4">
                    {sample.stages.map((stage, index) => (
                        <div key={stage.stage}>
                            {index > 0 && (
                                <div className="flex justify-center py-1">
                                    <ArrowDown className="h-5 w-5 text-muted-foreground" />
                                </div>
                            )}
                            <Card>
                                <CardHeader>
                                    <div className="flex items-center justify-between gap-3">
                                        <CardTitle className="flex items-center gap-2 text-base capitalize">
                                            <FileCode2 className="h-4 w-4" />
                                            {stage.stage.replace("-", " ")}
                                        </CardTitle>
                                        <Badge
                                            variant={
                                                stage.status === "passed"
                                                    ? "default"
                                                    : "destructive"
                                            }
                                        >
                                            {stage.status === "passed" ? (
                                                <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
                                            ) : (
                                                <XCircle className="mr-1 h-3.5 w-3.5" />
                                            )}
                                            {stage.status}
                                        </Badge>
                                    </div>
                                    <CardDescription>
                                        Generated result compared with the
                                        approved Golden artifact ·{" "}
                                        {stage.durationMs ?? 0} ms.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="grid gap-3 md:grid-cols-2">
                                    <div>
                                        <div className="mb-1 text-xs font-medium text-muted-foreground">
                                            ACTUAL
                                        </div>
                                        <pre className="min-h-[180px] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">
                                            {stage.actualSummary ??
                                                "Generated artifact"}
                                        </pre>
                                    </div>
                                    <div>
                                        <div className="mb-1 text-xs font-medium text-muted-foreground">
                                            GOLDEN
                                        </div>
                                        <pre className="min-h-[180px] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap">
                                            {stage.goldenSummary ??
                                                "Golden artifact"}
                                        </pre>
                                    </div>
                                </CardContent>
                            </Card>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
