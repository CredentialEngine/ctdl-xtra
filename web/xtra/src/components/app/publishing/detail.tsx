import { Badge } from "@/components/ui/badge";
import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import ResizableTable from "@/components/ui/resizable-table";
import { publishRuns } from "@/mock-control-plane";
import { useParams } from "next/navigation";

export default function PublishRunDetail() {
    const { runId } = useParams<{ runId: string }>();
    // TODO(publishing-db): Load this publish run, current stage progress, failures, artifact refs, and publisher iteration id from PostgreSQL.
    // TODO(argo-events): Persist workflow stage events so this view can refresh from the DB without talking directly to Argo.
    // TODO(publisher-api): Store the publisher project response and created iteration id when the final handoff succeeds.
    const run = publishRuns.find((item) => item.id === runId);
    if (!run) return <div>Publish run not found.</div>;

    return (
        <div className="space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Publishing", href: "/publishing" },
                    { label: "ETL Runs", href: "/publishing" },
                    { label: run.id, href: `/publishing/${run.id}` },
                ]}
            />
            <div>
                <h1 className="text-2xl font-semibold">{run.id}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    {run.sourceName} · {run.strategyName} · {run.projectName}
                </p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Status</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <Badge>
                            {run.status === "succeeded"
                                ? "Completed"
                                : run.status}
                        </Badge>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Progress</CardTitle>
                    </CardHeader>
                    <CardContent className="text-2xl font-semibold">
                        {run.progressPercent}%
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Published</CardTitle>
                    </CardHeader>
                    <CardContent className="text-2xl font-semibold">
                        {run.succeededPages}
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <CardTitle className="text-sm">Failed</CardTitle>
                    </CardHeader>
                    <CardContent className="text-2xl font-semibold">
                        {run.failedPages}
                    </CardContent>
                </Card>
            </div>
            <section
                className="space-y-3"
                aria-labelledby="publish-stage-heading"
            >
                <div>
                    <h2
                        id="publish-stage-heading"
                        className="text-base font-semibold"
                    >
                        ETL workflow progress
                    </h2>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Progress from extraction through the publisher-project
                        handoff.
                    </p>
                </div>
                <ResizableTable
                    ariaLabel="Publishing ETL stages"
                    rowKey="stage"
                    pagination={false}
                    dataSource={run.stages}
                    columns={[
                        {
                            title: "Stage",
                            dataIndex: "stage",
                            key: "stage",
                            render: (v) =>
                                String(v)
                                    .replace("publish-ready", "Publish-ready")
                                    .replace("publisher", "Publisher"),
                        },
                        {
                            title: "Status",
                            dataIndex: "status",
                            key: "status",
                            render: (v) => (
                                <Badge
                                    variant={
                                        v === "failed"
                                            ? "destructive"
                                            : v === "succeeded"
                                              ? "default"
                                              : "secondary"
                                    }
                                >
                                    {v}
                                </Badge>
                            ),
                        },
                        {
                            title: "Completed",
                            dataIndex: "completed",
                            key: "completed",
                            render: (v, stage) => `${v} / ${stage.total}`,
                        },
                        {
                            title: "Progress",
                            key: "progress",
                            render: (_, stage) =>
                                `${stage.total ? Math.round((stage.completed / stage.total) * 100) : 0}%`,
                        },
                    ]}
                />
            </section>
            {run.publisherIterationId && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">
                            Publisher result
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm">
                        <span className="text-muted-foreground">
                            Created iteration:{" "}
                        </span>
                        <span className="font-mono">
                            {run.publisherIterationId}
                        </span>
                    </CardContent>
                </Card>
            )}
            {run.error && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Failure</CardTitle>
                    </CardHeader>
                    <CardContent className="text-sm text-destructive">
                        {run.error}
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
