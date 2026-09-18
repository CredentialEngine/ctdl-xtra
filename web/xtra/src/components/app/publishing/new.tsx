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
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import {
    benchmarkStrategies,
    extractStrategies,
    getEffectiveCrawlRunId,
    getEffectiveDiscoveredPages,
    publishStrategies,
    sourceStrategyAssignments,
    sources,
    transformStrategies,
} from "@/mock-control-plane";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

function optionName(options: { id: string; name: string }[], id: string) {
    return options.find((option) => option.id === id)?.name ?? id;
}

export default function PublishRunNew() {
    const router = useRouter();
    const { toast } = useToast();
    const eligibleSources = sources.filter((source) =>
        getEffectiveDiscoveredPages(source.id).some(
            (page) =>
                !page.labels.includes("Ignore") &&
                !page.labels.includes("Unclassified"),
        ),
    );
    const [sourceId, setSourceId] = useState("");
    const [strategyId, setStrategyId] = useState("");
    const [projectId, setProjectId] = useState("");

    // TODO(source-strategy-db): Load only admin-promoted Source ↔ Strategy assignments. Publishing must not accept an unassigned strategy.
    // TODO(projects-api): Load publishable project ids + names from the publisher/Registry project service.
    const promotedStrategies = useMemo(() => {
        const assignedIds = new Set(
            sourceStrategyAssignments
                .filter((assignment) => assignment.sourceId === sourceId)
                .map((assignment) => assignment.strategyId),
        );
        return benchmarkStrategies.filter(
            (strategy) =>
                assignedIds.has(strategy.id) && strategy.status === "active",
        );
    }, [sourceId]);
    const strategy = promotedStrategies.find((item) => item.id === strategyId);
    const selectedPages = sourceId
        ? getEffectiveDiscoveredPages(sourceId).filter(
              (page) =>
                  !page.labels.includes("Ignore") &&
                  !page.labels.includes("Unclassified"),
          )
        : [];
    const effectiveCrawlRunId = sourceId
        ? getEffectiveCrawlRunId(sourceId)
        : undefined;

    function changeSource(value: string) {
        setSourceId(value);
        setStrategyId("");
    }

    function publish() {
        // TODO(publishing-api): Resolve the Source effective crawl cache (explicit LKG, otherwise latest successful), then create ONE publish run using only its persisted interesting/discovered pages and the exact promoted ETL strategy snapshot identified by strategyId.
        // TODO(publishing-api): Launch an Argo-backed ETL workflow that processes every publishable page, then sends the final output artifact to the publisher project endpoint.
        // TODO(argo-events): Accept workflow events in the API and update persisted stage progress/status as Extract, Transform, Publish-ready, and Publisher stages advance.
        // TODO(publisher-api): Call the destination project endpoint with the final artifact and persist the created project iteration id.
        // TODO(publishing-db): Persist run status, per-page ETL artifacts, counters, failures, immutable strategy snapshot, publisher responses, and iteration id for audit.
        toast({
            title: "Publishing endpoint not connected",
            description:
                "Would run the promoted strategy across every publishable page in this Source.",
        });
        router.push("/publishing");
    }

    return (
        <div className="mx-auto max-w-3xl space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Publishing", href: "/publishing" },
                    { label: "ETL Runs", href: "/publishing" },
                    { label: "Start run", href: "/publishing/new" },
                ]}
            />
            <div>
                <h1 className="text-2xl font-semibold">Start ETL run</h1>
                <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
                    Choose a Source, an admin-approved Strategy for that Source,
                    and a destination project.
                </p>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Publish inputs</CardTitle>
                    <CardDescription>
                        Publishing runs the selected promoted Strategy across
                        the entire publishable discovered-page set.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="space-y-2">
                        <Label>Source</Label>
                        <Select value={sourceId} onValueChange={changeSource}>
                            <SelectTrigger>
                                <SelectValue placeholder="Choose a discovered Source" />
                            </SelectTrigger>
                            <SelectContent>
                                {eligibleSources.map((source) => {
                                    const count = getEffectiveDiscoveredPages(
                                        source.id,
                                    ).filter(
                                        (page) =>
                                            !page.labels.includes("Ignore") &&
                                            !page.labels.includes(
                                                "Unclassified",
                                            ),
                                    ).length;
                                    return (
                                        <SelectItem
                                            key={source.id}
                                            value={source.id}
                                        >
                                            {source.name} · {count} discovered
                                            pages
                                        </SelectItem>
                                    );
                                })}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="space-y-2">
                        <Label>Strategy</Label>
                        <Select
                            value={strategyId}
                            onValueChange={setStrategyId}
                            disabled={!sourceId}
                        >
                            <SelectTrigger>
                                <SelectValue
                                    placeholder={
                                        sourceId
                                            ? "Choose a promoted Strategy"
                                            : "Choose a Source first"
                                    }
                                />
                            </SelectTrigger>
                            <SelectContent>
                                {promotedStrategies.map((item) => (
                                    <SelectItem key={item.id} value={item.id}>
                                        {item.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {sourceId && !promotedStrategies.length && (
                            <p className="text-xs text-muted-foreground">
                                No promoted Strategies yet. Benchmark and
                                promote a Strategy before publishing this
                                Source.
                            </p>
                        )}
                    </div>

                    {strategy && (
                        <div className="rounded-lg bg-muted/40 p-4">
                            <div className="flex items-center gap-2">
                                <div className="font-semibold">
                                    {strategy.name}
                                </div>
                                <Badge>Promoted</Badge>
                            </div>
                            <div className="mt-4 grid gap-3 md:grid-cols-3">
                                <div>
                                    <div className="text-xs text-muted-foreground">
                                        Extract
                                    </div>
                                    <div className="mt-1 text-sm font-medium">
                                        {optionName(
                                            extractStrategies,
                                            strategy.extractOptionId,
                                        )}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-xs text-muted-foreground">
                                        Transform
                                    </div>
                                    <div className="mt-1 text-sm font-medium">
                                        {optionName(
                                            transformStrategies,
                                            strategy.transformOptionId,
                                        )}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-xs text-muted-foreground">
                                        Publish-ready
                                    </div>
                                    <div className="mt-1 text-sm font-medium">
                                        {optionName(
                                            publishStrategies,
                                            strategy.publishReadyOptionId,
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    {sourceId && (
                        <div className="rounded-lg bg-muted/40 p-4 text-sm">
                            <div className="font-medium">
                                Effective crawl cache
                            </div>
                            <div className="mt-1 text-muted-foreground">
                                {effectiveCrawlRunId ?? "None"} ·{" "}
                                {selectedPages.length} publishable discovered
                                pages
                            </div>
                        </div>
                    )}

                    <div className="space-y-2">
                        <Label>Destination project</Label>
                        <Select value={projectId} onValueChange={setProjectId}>
                            <SelectTrigger>
                                <SelectValue placeholder="Choose a project" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="project-registry-101">
                                    Northstar Registry Project
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="flex justify-end gap-2">
                        <Button variant="outline" asChild>
                            <Link href="/publishing">Cancel</Link>
                        </Button>
                        <Button
                            onClick={publish}
                            disabled={!sourceId || !strategyId || !projectId}
                        >
                            Start ETL run
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
