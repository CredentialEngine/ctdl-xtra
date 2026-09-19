import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import ResizableTable from "@/components/ui/resizable-table";
import { useSnackbar } from "@/components/ui/snackbar-provider";
import {
    benchmarkRuns,
    benchmarkStrategies,
    extractStrategies,
    publishStrategies,
    sourceStrategyAssignments,
    sources,
    transformStrategies,
} from "@/mock-control-plane";
import Plus from "@mui/icons-material/Add";
import { Box } from "@mui/material";
import MuiBox from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";
import MuiTypography from "@mui/material/Typography";

function optionName(options: { id: string; name: string }[], id: string) {
    return options.find((option) => option.id === id)?.name ?? id;
}

export default function BenchmarkStrategies() {
    const { showSnackbar } = useSnackbar();
    // TODO(strategy-api): GET global immutable ETL strategy definitions and available extractor/transform/publish-ready choices.
    // TODO(strategy-db): Persist strategy definitions independently of Sources.
    // TODO(benchmark-db): Load latest benchmark summaries by strategy across Sources.
    // TODO(source-strategy-db): Load admin-approved Source ↔ Strategy assignments used by Publishing.

    function createStrategy() {
        showSnackbar({
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
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Strategies", href: "/benchmarks/strategies" },
                ]}
            />
            <Box className="flex flex-wrap items-end justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        Strategies
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 max-w-3xl text-sm text-muted-foreground"
                    >
                        Strategies are reusable Extract → Transform →
                        Publish-ready definitions. They do not belong to a
                        Source. Benchmark Runs test them against the Promoted
                        Golden Samples for a Source.
                    </MuiTypography>
                </Box>
                <Box className="flex flex-wrap items-center gap-2">
                    <Button variant="outline" onClick={createStrategy}>
                        <Plus className="mr-2 h-4 w-4" />
                        New strategy
                    </Button>
                </Box>
            </Box>

            <MuiBox
                component="section"
                aria-labelledby="strategies-table-heading"
                className="space-y-3"
            >
                <Box>
                    <MuiTypography
                        variant="h2"
                        component="h2"
                        id="strategies-table-heading"
                        className="text-base font-semibold"
                    >
                        Strategies
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        Admins can promote/link a proven strategy to a Source
                        from a completed Benchmark Report. That link is what
                        makes it selectable in Publishing.
                    </MuiTypography>
                </Box>
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
                                <Tooltip
                                    title={row.description}
                                    arrow
                                    describeChild
                                >
                                    <Box
                                        component="span"
                                        tabIndex={0}
                                        className="font-medium"
                                        sx={{
                                            display: "inline-block",
                                            cursor: "help",
                                        }}
                                    >
                                        {row.name}
                                    </Box>
                                </Tooltip>
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
                                    <Box className="flex flex-wrap gap-1">
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
                                    </Box>
                                ) : (
                                    <MuiTypography
                                        component="span"
                                        className="text-sm text-muted-foreground"
                                    >
                                        None
                                    </MuiTypography>
                                ),
                        },
                    ]}
                />
            </MuiBox>
        </Box>
    );
}
