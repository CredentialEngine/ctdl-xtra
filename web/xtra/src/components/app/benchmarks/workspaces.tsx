import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
import ResizableTable from "@/components/ui/resizable-table";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import {
    benchmarkRuns,
    getEffectiveDiscoveredPages,
    goldenSamples,
    sources,
} from "@/mock-control-plane";
import FileSearch from "@mui/icons-material/FindInPage";
import Link from "@/components/ui/route-link";

export default function BenchmarkWorkspaces() {
    // TODO(source-db): Load benchmarkable Sources and discovery summary from PostgreSQL.
    // TODO(benchmark-db): Load golden-set, strategy, and latest benchmark summary counts per Source.
    const rows = sources.map((source) => {
        const pages = getEffectiveDiscoveredPages(source.id).filter(
            (page) =>
                !page.labels.includes("Ignore") &&
                !page.labels.includes("Unclassified"),
        );
        const golden = goldenSamples.filter(
            (sample) => sample.sourceId === source.id,
        );
        const latestRun = benchmarkRuns.find(
            (run) => run.sourceId === source.id,
        );
        return {
            ...source,
            usefulPages: pages.length,
            goldenCount: golden.length || source.goldenSamples,
            latestRun,
        };
    });

    return (
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Workspaces", href: "/benchmarks/workspaces" },
                ]}
            />
            <Box>
                <MuiTypography
                    variant="h1"
                    component="h1"
                    className="text-2xl font-semibold"
                >
                    Workspaces
                </MuiTypography>
                <MuiTypography
                    component="p"
                    className="mt-1 max-w-3xl text-sm text-muted-foreground"
                >
                    Start from a Source, review the discovered pages from its
                    effective crawl cache, and build its Promoted Golden Sample
                    Set. Reusable ETL strategies are managed separately under
                    Strategies.
                </MuiTypography>
            </Box>

            <ResizableTable
                ariaLabel="Benchmark workspaces"
                rowKey="id"
                size="middle"
                dataSource={rows}
                pagination={{ defaultPageSize: 20, showSizeChanger: true }}
                columns={[
                    {
                        title: "Source",
                        key: "source",
                        sorter: {
                            compare: (a, b) => a.name.localeCompare(b.name),
                            multiple: 5,
                        },
                        render: (_, row) => (
                            <Box>
                                <Link
                                    href={`/benchmarks/workspaces/${row.id}`}
                                    className="font-medium hover:underline focus-visible:underline"
                                >
                                    {row.name}
                                </Link>
                                <Box className="mt-0.5 max-w-[520px] truncate text-xs text-muted-foreground">
                                    {row.url}
                                </Box>
                            </Box>
                        ),
                    },
                    {
                        title: "Organization",
                        dataIndex: "organizationName",
                        key: "organization",
                        sorter: {
                            compare: (a, b) =>
                                a.organizationName.localeCompare(
                                    b.organizationName,
                                ),
                            multiple: 4,
                        },
                    },
                    {
                        title: "Discovered",
                        dataIndex: "usefulPages",
                        key: "discovered",
                        width: 125,
                        sorter: {
                            compare: (a, b) => a.usefulPages - b.usefulPages,
                            multiple: 3,
                        },
                        render: (value) => (
                            <MuiTypography
                                component="span"
                                className="inline-flex items-center gap-1.5"
                            >
                                <FileSearch className="h-4 w-4 text-muted-foreground" />
                                {value}
                            </MuiTypography>
                        ),
                    },
                    {
                        title: "Promoted Golden",
                        dataIndex: "goldenCount",
                        key: "golden",
                        width: 110,
                        sorter: {
                            compare: (a, b) => a.goldenCount - b.goldenCount,
                            multiple: 2,
                        },
                        render: (value) => (
                            <MuiTypography component="span">
                                {value}
                            </MuiTypography>
                        ),
                    },
                    {
                        title: "Latest run",
                        key: "latestRun",
                        width: 170,
                        filters: [
                            { text: "Completed", value: "completed" },
                            { text: "Failed", value: "failed" },
                            { text: "Running", value: "running" },
                            { text: "Queued", value: "queued" },
                            { text: "No runs", value: "none" },
                        ],
                        onFilter: (value, row) =>
                            (row.latestRun?.status ?? "none") === value,
                        render: (_, row) =>
                            row.latestRun ? (
                                <Badge
                                    variant={
                                        row.latestRun.status === "failed"
                                            ? "destructive"
                                            : row.latestRun.status ===
                                                "completed"
                                              ? "default"
                                              : "secondary"
                                    }
                                    className="whitespace-nowrap capitalize"
                                >
                                    {row.latestRun.status}
                                </Badge>
                            ) : (
                                <MuiTypography
                                    component="span"
                                    className="text-sm text-muted-foreground"
                                >
                                    No runs
                                </MuiTypography>
                            ),
                    },
                ]}
            />
        </Box>
    );
}
