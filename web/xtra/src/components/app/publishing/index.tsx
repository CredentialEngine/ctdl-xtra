import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import ResizableTable from "@/components/ui/resizable-table";
import type { PublishRun } from "@/domain";
import { publishRuns } from "@/mock-control-plane";
import Link from "@/components/ui/route-link";

function PublishStatus({ status }: { status: PublishRun["status"] }) {
    const variant =
        status === "failed"
            ? "destructive"
            : status === "succeeded"
              ? "default"
              : "secondary";
    return (
        <Badge variant={variant}>
            {status === "succeeded"
                ? "Completed"
                : status[0].toUpperCase() + status.slice(1)}
        </Badge>
    );
}

export default function Publishing() {
    // TODO(publishing-db): Load publish runs with Source, promoted strategy snapshot, project, progress, stage counters, publisher iteration id, timestamps, and errors.
    // TODO(argo-events): Argo workflow callbacks update publish-run status and ETL progress in PostgreSQL via the API.
    const rows = [...publishRuns].sort(
        (a, b) =>
            new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime(),
    );

    return (
        <Box className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Publishing", href: "/publishing" },
                    { label: "ETL Runs", href: "/publishing/runs" },
                ]}
            />
            <Box className="flex flex-wrap items-end justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        ETL Runs
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 max-w-3xl text-sm text-muted-foreground"
                    >
                        Track publishing ETL runs through extraction,
                        transformation, publish-ready output, and the final
                        publisher-project iteration.
                    </MuiTypography>
                </Box>
                <Button asChild>
                    <Link href="/publishing/new">Start ETL run</Link>
                </Button>
            </Box>
            <ResizableTable<PublishRun>
                ariaLabel="Publishing ETL runs"
                rowKey="id"
                dataSource={rows}
                pagination={{ defaultPageSize: 20, showSizeChanger: true }}
                columns={[
                    {
                        title: "Run",
                        dataIndex: "id",
                        key: "id",
                        width: 175,
                        sorter: {
                            compare: (a, b) => a.id.localeCompare(b.id),
                            multiple: 7,
                        },
                        render: (value, run) => (
                            <Link
                                href={`/publishing/${run.id}`}
                                className="font-mono text-xs font-medium hover:underline"
                            >
                                {value}
                            </Link>
                        ),
                    },
                    {
                        title: "Source",
                        dataIndex: "sourceName",
                        key: "source",
                        width: 190,
                        filterSearch: true,
                        filters: [
                            ...new Set(rows.map((r) => r.sourceName)),
                        ].map((v) => ({ text: v, value: v })),
                        onFilter: (v, r) => r.sourceName === v,
                        sorter: {
                            compare: (a, b) =>
                                a.sourceName.localeCompare(b.sourceName),
                            multiple: 6,
                        },
                    },
                    {
                        title: "Strategy",
                        dataIndex: "strategyName",
                        key: "strategy",
                        width: 160,
                        filters: [
                            ...new Set(rows.map((r) => r.strategyName)),
                        ].map((v) => ({ text: v, value: v })),
                        onFilter: (v, r) => r.strategyName === v,
                        sorter: {
                            compare: (a, b) =>
                                a.strategyName.localeCompare(b.strategyName),
                            multiple: 5,
                        },
                    },
                    {
                        title: "Project",
                        dataIndex: "projectName",
                        key: "project",
                        width: 180,
                        hidden: true,
                        sorter: {
                            compare: (a, b) =>
                                a.projectName.localeCompare(b.projectName),
                            multiple: 4,
                        },
                    },
                    {
                        title: "Status",
                        dataIndex: "status",
                        key: "status",
                        width: 105,
                        filters: [
                            "queued",
                            "running",
                            "succeeded",
                            "failed",
                        ].map((v) => ({ text: v, value: v })),
                        onFilter: (v, r) => r.status === v,
                        sorter: {
                            compare: (a, b) => a.status.localeCompare(b.status),
                            multiple: 3,
                        },
                        render: (value) => <PublishStatus status={value} />,
                    },
                    {
                        title: "Progress",
                        dataIndex: "progressPercent",
                        key: "progress",
                        width: 95,
                        sorter: {
                            compare: (a, b) =>
                                a.progressPercent - b.progressPercent,
                            multiple: 2,
                        },
                        render: (v) => `${v}%`,
                    },
                    {
                        title: "Pages",
                        dataIndex: "totalPages",
                        key: "pages",
                        width: 80,
                        sorter: {
                            compare: (a, b) => a.totalPages - b.totalPages,
                            multiple: 1,
                        },
                    },
                    {
                        title: "Started",
                        dataIndex: "startedAt",
                        key: "started",
                        width: 160,
                        defaultSortOrder: "descend",
                        sorter: {
                            compare: (a, b) =>
                                new Date(a.startedAt).getTime() -
                                new Date(b.startedAt).getTime(),
                            multiple: 8,
                        },
                        render: (v) => new Date(v).toLocaleString(),
                    },
                ]}
            />
        </Box>
    );
}
