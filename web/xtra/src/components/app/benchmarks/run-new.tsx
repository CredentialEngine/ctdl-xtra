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
    getEffectiveDiscoveredPages,
    goldenSamples,
    sources,
} from "@/mock-control-plane";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function BenchmarkRunNew() {
    const router = useRouter();
    const { toast } = useToast();
    const [sourceId, setSourceId] = useState("");
    const [strategyId, setStrategyId] = useState("");
    const activeStrategies = benchmarkStrategies.filter(
        (strategy) => strategy.status === "active",
    );
    const selectedSource = sources.find((source) => source.id === sourceId);
    const selectedStrategy = activeStrategies.find(
        (strategy) => strategy.id === strategyId,
    );
    const goldenCount =
        goldenSamples.filter((sample) => sample.sourceId === sourceId).length ||
        selectedSource?.goldenSamples ||
        0;

    function startRun() {
        if (!sourceId || !strategyId) return;
        // TODO(benchmark-api): POST { sourceId, strategyId }. Resolve the current Promoted Golden Sample Set,
        // resolve each Golden Sample source document against the Source effective crawl cache (LKG, otherwise latest successful), snapshot the Strategy, enqueue one benchmark job, and return benchmarkRunId.
        toast({
            title: "Benchmark endpoint not connected",
            description: `Would run ${selectedStrategy?.name} against ${goldenCount} promoted Golden Samples for ${selectedSource?.name}.`,
        });
        router.push("/benchmarks/runs");
    }

    return (
        <div className="mx-auto max-w-3xl space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Runs", href: "/benchmarks/runs" },
                    { label: "Start run", href: "/benchmarks/runs/new" },
                ]}
            />
            <div>
                <h1 className="text-2xl font-semibold">Start benchmark run</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    Choose a Source and an existing Strategy. The benchmark runs
                    that Strategy against the Source&apos;s complete Promoted
                    Golden Sample Set.
                </p>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">
                        Benchmark inputs
                    </CardTitle>
                    <CardDescription>
                        Strategies are reusable and global; the Source supplies
                        the Golden Sample Set used by this run.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                    <div className="space-y-2">
                        <Label>Source</Label>
                        <Select value={sourceId} onValueChange={setSourceId}>
                            <SelectTrigger aria-label="Source">
                                <SelectValue placeholder="Choose Source" />
                            </SelectTrigger>
                            <SelectContent>
                                {sources
                                    .filter((source) =>
                                        getEffectiveDiscoveredPages(
                                            source.id,
                                        ).some(
                                            (page) =>
                                                !page.labels.includes(
                                                    "Ignore",
                                                ) &&
                                                !page.labels.includes(
                                                    "Unclassified",
                                                ),
                                        ),
                                    )
                                    .map((source) => (
                                        <SelectItem
                                            key={source.id}
                                            value={source.id}
                                        >
                                            {source.name}
                                        </SelectItem>
                                    ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label>Strategy</Label>
                        <Select
                            value={strategyId}
                            onValueChange={setStrategyId}
                        >
                            <SelectTrigger aria-label="Strategy">
                                <SelectValue placeholder="Choose Strategy" />
                            </SelectTrigger>
                            <SelectContent>
                                {activeStrategies.map((strategy) => (
                                    <SelectItem
                                        key={strategy.id}
                                        value={strategy.id}
                                    >
                                        {strategy.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    {sourceId && (
                        <div className="rounded-md bg-muted/40 p-3 text-sm">
                            <span className="font-medium">
                                Promoted Golden Samples in scope:
                            </span>{" "}
                            {goldenCount}
                        </div>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" asChild>
                            <Link href="/benchmarks/runs">Cancel</Link>
                        </Button>
                        <Button
                            onClick={startRun}
                            disabled={!sourceId || !strategyId}
                        >
                            Run benchmark
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
