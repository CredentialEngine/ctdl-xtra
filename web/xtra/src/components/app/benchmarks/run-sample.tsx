import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
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
import ArrowDown from "@mui/icons-material/ArrowDownward";
import CheckCircle2 from "@mui/icons-material/CheckCircle";
import FileCode2 from "@mui/icons-material/DataObject";
import FileText from "@mui/icons-material/Description";
import XCircle from "@mui/icons-material/Cancel";
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
    if (!run || !sample) return <Box>Benchmark sample result not found.</Box>;

    return (
        <Box className="space-y-6">
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
            <Box className="flex flex-wrap items-end justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        Sample Audit
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        {sample.pageTitle}
                    </MuiTypography>
                </Box>
            </Box>

            <Box className="grid gap-6 xl:grid-cols-2 xl:items-start">
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
                        <MuiBox
                            component="pre"
                            className="max-h-[720px] overflow-auto rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap"
                        >{`SOURCE: ${sample.pageUrl}\n\n${sample.pageTitle}`}</MuiBox>
                    </CardContent>
                </Card>

                <Box className="space-y-4">
                    {sample.stages.map((stage, index) => (
                        <Box key={stage.stage}>
                            {index > 0 && (
                                <Box className="flex justify-center py-1">
                                    <ArrowDown className="h-5 w-5 text-muted-foreground" />
                                </Box>
                            )}
                            <Card>
                                <CardHeader>
                                    <Box className="flex items-center justify-between gap-3">
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
                                    </Box>
                                    <CardDescription>
                                        Generated result compared with the
                                        approved Golden artifact ·{" "}
                                        {stage.durationMs ?? 0} ms.
                                    </CardDescription>
                                </CardHeader>
                                <CardContent className="grid gap-3 md:grid-cols-2">
                                    <Box>
                                        <Box className="mb-1 text-xs font-medium text-muted-foreground">
                                            ACTUAL
                                        </Box>
                                        <MuiBox
                                            component="pre"
                                            className="min-h-[180px] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap"
                                        >
                                            {stage.actualSummary ??
                                                "Generated artifact"}
                                        </MuiBox>
                                    </Box>
                                    <Box>
                                        <Box className="mb-1 text-xs font-medium text-muted-foreground">
                                            GOLDEN
                                        </Box>
                                        <MuiBox
                                            component="pre"
                                            className="min-h-[180px] overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap"
                                        >
                                            {stage.goldenSummary ??
                                                "Golden artifact"}
                                        </MuiBox>
                                    </Box>
                                </CardContent>
                            </Card>
                        </Box>
                    ))}
                </Box>
            </Box>
        </Box>
    );
}
