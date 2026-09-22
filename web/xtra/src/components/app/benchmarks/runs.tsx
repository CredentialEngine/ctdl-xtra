import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
import ResizableTable from "@/components/ui/resizable-table";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import { benchmarkRuns } from "@/mock-control-plane";
import Clock3 from "@mui/icons-material/Schedule";
import Link from "@/components/ui/route-link";

function score(run: (typeof benchmarkRuns)[number]) {
    if (!run.samples) return 0;
    return Math.round((run.passed / run.samples) * 1000) / 10;
}

export default function BenchmarkRuns() {
    // TODO(benchmark-db): GET benchmark jobs across Sources, with status, strategy snapshot, score/report summary, timestamps, and progress counters.
    const rows = [...benchmarkRuns].sort(
        (a, b) =>
            new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    );

    return (
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Runs", href: "/benchmarks/runs" },
                ]}
            />
            <Box className="flex flex-wrap items-end justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        Runs
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 max-w-3xl text-sm text-muted-foreground"
                    >
                        Monitor benchmark jobs that run a selected Strategy
                        against a Source&apos;s Promoted Golden Sample Set.
                    </MuiTypography>
                </Box>
                <Button asChild>
                    <Link href="/benchmarks/runs/new">Start benchmark run</Link>
                </Button>
            </Box>

            <MuiBox component="section" aria-label="Benchmark run history">
                <ResizableTable
                    ariaLabel="Benchmark runs"
                    rowKey="id"
                    size="middle"
                    dataSource={rows}
                    pagination={{ defaultPageSize: 25, showSizeChanger: true }}
                    columns={[
                        {
                            title: "Run",
                            dataIndex: "id",
                            key: "id",
                            sorter: {
                                compare: (a, b) => a.id.localeCompare(b.id),
                                multiple: 6,
                            },
                            render: (value, run) => (
                                <Link
                                    href={`/benchmarks/runs/${run.id}`}
                                    className="font-mono text-xs font-medium hover:underline focus-visible:underline"
                                >
                                    {value}
                                </Link>
                            ),
                        },
                        {
                            title: "Source",
                            dataIndex: "sourceName",
                            key: "source",
                            filters: [
                                ...new Set(rows.map((run) => run.sourceName)),
                            ].map((value) => ({ text: value, value })),
                            filterSearch: true,
                            onFilter: (value, run) => run.sourceName === value,
                            sorter: {
                                compare: (a, b) =>
                                    a.sourceName.localeCompare(b.sourceName),
                                multiple: 5,
                            },
                        },
                        {
                            title: "Strategy",
                            dataIndex: "strategyName",
                            key: "strategy",
                            filters: [
                                ...new Set(rows.map((run) => run.strategyName)),
                            ].map((value) => ({ text: value, value })),
                            filterSearch: true,
                            onFilter: (value, run) =>
                                run.strategyName === value,
                            sorter: {
                                compare: (a, b) =>
                                    a.strategyName.localeCompare(
                                        b.strategyName,
                                    ),
                                multiple: 4,
                            },
                        },
                        {
                            title: "Status",
                            dataIndex: "status",
                            key: "status",
                            width: 125,
                            filters: [
                                "queued",
                                "running",
                                "completed",
                                "failed",
                            ].map((value) => ({
                                text: value[0].toUpperCase() + value.slice(1),
                                value,
                            })),
                            onFilter: (value, run) => run.status === value,
                            sorter: {
                                compare: (a, b) =>
                                    a.status.localeCompare(b.status),
                                multiple: 3,
                            },
                            render: (value) => (
                                <Badge
                                    variant={
                                        value === "failed"
                                            ? "destructive"
                                            : value === "completed"
                                              ? "default"
                                              : "secondary"
                                    }
                                    className="whitespace-nowrap capitalize"
                                >
                                    {value}
                                </Badge>
                            ),
                        },
                        {
                            title: "Samples",
                            dataIndex: "samples",
                            key: "samples",
                            width: 90,
                            sorter: {
                                compare: (a, b) => a.samples - b.samples,
                                multiple: 2,
                            },
                        },
                        {
                            title: "Score",
                            key: "score",
                            width: 95,
                            sorter: {
                                compare: (a, b) => score(a) - score(b),
                                multiple: 1,
                            },
                            render: (_, run) =>
                                run.status === "failed"
                                    ? "—"
                                    : `${score(run)}%`,
                        },
                        {
                            title: "Started",
                            dataIndex: "startedAt",
                            key: "started",
                            width: 180,
                            sorter: {
                                compare: (a, b) =>
                                    new Date(a.startedAt).getTime() -
                                    new Date(b.startedAt).getTime(),
                                multiple: 7,
                            },
                            defaultSortOrder: "descend" as const,
                            render: (value) => (
                                <MuiTypography
                                    component="span"
                                    className="inline-flex items-center gap-1.5 text-sm"
                                >
                                    <Clock3
                                        className="h-3.5 w-3.5 text-muted-foreground"
                                        aria-hidden="true"
                                    />
                                    {new Date(value).toLocaleString()}
                                </MuiTypography>
                            ),
                        },
                    ]}
                />
            </MuiBox>
        </Box>
    );
}
