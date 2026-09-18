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
    discoveredPages,
    extractStrategies,
    publishStrategies,
    sources,
    transformStrategies,
} from "@/mock-control-plane";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

function optionName(options: { id: string; name: string }[], id?: string) {
    return options.find((option) => option.id === id)?.name ?? id ?? "—";
}

export default function BenchmarkPageRun() {
    const { sourceId, pageId } = useParams<{
        sourceId: string;
        pageId: string;
    }>();
    const router = useRouter();
    const { toast } = useToast();
    const source = sources.find((item) => item.id === sourceId);
    const page = discoveredPages.find(
        (item) => item.id === pageId && item.sourceId === sourceId,
    );
    const strategies = benchmarkStrategies.filter(
        (strategy) => strategy.status === "active",
    );
    const [strategyId, setStrategyId] = useState("");
    const strategy = useMemo(
        () => strategies.find((item) => item.id === strategyId),
        [strategies, strategyId],
    );

    if (!source || !page) return <div>Discovered page not found.</div>;
    const currentSource = source;
    const currentPage = page;

    function runEtl() {
        if (!strategyId) return;
        // TODO(benchmark-api): POST a repeatable single-page ETL execution with { sourceId, pageId, strategyId }.
        // Persist an immutable Strategy snapshot plus Source/Extract/Transform/Publish-ready artifacts and return executionId.
        toast({
            title: "Single-page ETL endpoint not connected",
            description: `Would run ${strategy?.name} on ${currentPage.title}.`,
        });
        // TODO(benchmark-api): navigate with the returned executionId so Audit can inspect that exact execution rather than "latest".
        router.push(
            `/benchmarks/workspaces/${currentSource.id}/pages/${currentPage.id}`,
        );
    }

    return (
        <div className="mx-auto max-w-3xl space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Benchmarks", href: "/benchmarks" },
                    { label: "Workspaces", href: "/benchmarks/workspaces" },
                    {
                        label: source.name,
                        href: `/benchmarks/workspaces/${source.id}`,
                    },
                    {
                        label: page.title,
                        href: `/benchmarks/workspaces/${source.id}/pages/${page.id}`,
                    },
                    {
                        label: "Run",
                        href: `/benchmarks/workspaces/${source.id}/pages/${page.id}/run`,
                    },
                ]}
            />

            <div>
                <h1 className="text-2xl font-semibold">{source.name}</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    {source.url}
                </p>
            </div>

            <div className="rounded-lg bg-muted/35 p-4">
                <div className="font-semibold">{page.title}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                    {page.url}
                </div>
                <div className="mt-3 flex flex-wrap gap-1">
                    {page.labels.map((label) => (
                        <Badge key={label} variant="outline">
                            {label}
                        </Badge>
                    ))}
                </div>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="text-base">
                        Run ETL on this page
                    </CardTitle>
                    <CardDescription>
                        Choose an existing Strategy. Every execution is
                        independent, so you can rerun this page as often as
                        needed and audit each resulting artifact set.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
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
                                {strategies.map((item) => (
                                    <SelectItem key={item.id} value={item.id}>
                                        {item.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {strategy && (
                        <div className="grid gap-3 rounded-lg bg-muted/35 p-4 md:grid-cols-3">
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
                    )}

                    <div className="flex justify-end gap-2">
                        <Button variant="outline" asChild>
                            <Link href={`/benchmarks/workspaces/${source.id}`}>
                                Cancel
                            </Link>
                        </Button>
                        <Button onClick={runEtl} disabled={!strategyId}>
                            Run ETL
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
