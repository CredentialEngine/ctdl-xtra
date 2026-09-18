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
import { crawlStrategies, sources } from "@/mock-control-plane";
import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

export default function CrawlRunNew() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { toast } = useToast();
    const querySourceId = searchParams.get("sourceId") ?? "";
    const [sourceId, setSourceId] = useState(querySourceId);
    const [strategyId, setStrategyId] = useState("");
    const selectedSource = sources.find((source) => source.id === sourceId);

    // TODO(crawl-strategy-api): Load active crawler strategies (Playwright, AI-agent, HTTP, custom) from the strategy/config service.
    function start() {
        // TODO(crawl-api): POST { sourceId, strategyId } to create the crawl run and launch its Argo workflow.
        // TODO(crawl-db): Persist the crawl run, strategy snapshot, initial queued status, progress counters, and workflow id in PostgreSQL.
        // TODO(argo-events): Accept workflow events in the API and update status/progress/error/timestamps as the crawl advances.
        toast({
            title: "Crawl run queued",
            description: "The backend integration is not connected yet.",
        });
        router.push(sourceId ? `/sources/${sourceId}` : "/crawls");
    }

    return (
        <div className="mx-auto max-w-3xl space-y-6">
            <BreadcrumbTrail
                items={
                    selectedSource
                        ? [
                              { label: "Sources", href: "/sources" },
                              {
                                  label: selectedSource.name,
                                  href: `/sources/${selectedSource.id}`,
                              },
                              { label: "Start crawl", href: "/crawls/new" },
                          ]
                        : [
                              { label: "Sources", href: "/sources" },
                              { label: "Crawl Runs", href: "/crawls" },
                              { label: "Start crawl", href: "/crawls/new" },
                          ]
                }
            />
            <div>
                <h1 className="text-2xl font-semibold">Start crawl</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    Choose the Source and crawler strategy. Starting a crawl
                    only queues that crawl; discovery will not start
                    automatically.
                </p>
            </div>
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Crawl inputs</CardTitle>
                    <CardDescription>
                        Each run records the exact strategy and produces a
                        timestamped cache when successful.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                    <div className="space-y-2">
                        <Label>Source</Label>
                        <Select value={sourceId} onValueChange={setSourceId}>
                            <SelectTrigger>
                                <SelectValue placeholder="Choose a Source" />
                            </SelectTrigger>
                            <SelectContent>
                                {sources.map((source) => (
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
                        <Label>Crawl strategy</Label>
                        <Select
                            value={strategyId}
                            onValueChange={setStrategyId}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Choose a crawl strategy" />
                            </SelectTrigger>
                            <SelectContent>
                                {crawlStrategies
                                    .filter(
                                        (strategy) =>
                                            strategy.status === "active",
                                    )
                                    .map((strategy) => (
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
                    {strategyId && (
                        <div className="rounded-md bg-muted/50 p-4 text-sm text-muted-foreground">
                            {
                                crawlStrategies.find(
                                    (strategy) => strategy.id === strategyId,
                                )?.description
                            }
                        </div>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" asChild>
                            <Link
                                href={
                                    sourceId
                                        ? `/sources/${sourceId}`
                                        : "/crawls"
                                }
                            >
                                Cancel
                            </Link>
                        </Button>
                        <Button
                            disabled={!sourceId || !strategyId}
                            onClick={start}
                        >
                            Start crawl
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
