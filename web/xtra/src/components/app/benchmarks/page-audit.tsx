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
import { useToast } from "@/components/ui/use-toast";
import {
    benchmarkStrategies,
    discoveredPages,
    extractStrategies,
    publishStrategies,
    sources,
    transformStrategies,
} from "@/mock-control-plane";
import { ArrowDown, FileCode2, FileText, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

function optionName(options: { id: string; name: string }[], id?: string) {
    return options.find((option) => option.id === id)?.name ?? id ?? "—";
}

function mockSourceDocument(title: string, url: string) {
    return `<html>\n  <head><title>${title}</title></head>\n  <body>\n    <main>\n      <h1>${title}</h1>\n      <p>Source content captured from ${url}</p>\n      <section>Course or learning-opportunity content...</section>\n    </main>\n  </body>\n</html>`;
}

export default function BenchmarkPageAudit() {
    const { sourceId, pageId } = useParams<{
        sourceId: string;
        pageId: string;
    }>();
    const { toast } = useToast();
    // TODO(source-db): GET the cached source-document artifact for this discovered page/crawl snapshot.
    // TODO(benchmark-db): GET prior single-page ETL executions, select the requested/latest execution, and load any Golden Sample record.
    const source = sources.find((item) => item.id === sourceId);
    const page = discoveredPages.find(
        (item) => item.id === pageId && item.sourceId === sourceId,
    );
    const strategy = benchmarkStrategies.find(
        (item) => item.status === "active",
    );

    if (!source || !page) return <div>Discovered page not found.</div>;

    const hasRun =
        page.validationStatus === "ready_for_review" || page.isGolden;

    function promoteGolden() {
        // TODO(benchmark-db): Persist the source document, exact Strategy snapshot, and manually approved Extract/Transform/Publish-ready outputs as a Promoted Golden Sample for this Source.
        toast({
            title: "Golden Sample endpoint not connected",
            description:
                "Would promote this page and the reviewed outputs into the Source Promoted Golden Sample Set.",
        });
    }

    const artifacts = [
        {
            label: "Extract Output",
            body: JSON.stringify(
                {
                    name: page.title,
                    types: page.labels,
                    url: page.url,
                    description:
                        "Extracted structured fields from the source document.",
                },
                null,
                2,
            ),
        },
        {
            label: "Transform Output",
            body: JSON.stringify(
                {
                    "@type": page.labels.map((label) =>
                        label.replaceAll(" ", ""),
                    ),
                    name: page.title,
                    subjectWebpage: page.url,
                    normalized: true,
                },
                null,
                2,
            ),
        },
        {
            label: "Publish-ready Output",
            body: JSON.stringify(
                {
                    project: "project-id-placeholder",
                    action: "upsert",
                    resource: { name: page.title, types: page.labels },
                    validated: true,
                },
                null,
                2,
            ),
        },
    ];

    return (
        <div className="space-y-6">
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
                ]}
            />

            <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                    <h1 className="text-2xl font-semibold">{source.name}</h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {source.url}
                    </p>
                </div>
                <Button asChild>
                    <Link
                        href={`/benchmarks/workspaces/${source.id}/pages/${page.id}/run`}
                    >
                        Run again
                    </Link>
                </Button>
            </div>

            <div className="rounded-lg bg-muted/35 p-4">
                <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Page under review
                    </span>
                    <div className="flex flex-wrap gap-1">
                        {page.labels.map((label) => (
                            <Badge key={label} variant="outline">
                                {label}
                            </Badge>
                        ))}
                    </div>
                    {page.isGolden && <Badge>Promoted Golden</Badge>}
                </div>
                <div className="mt-1 font-semibold">{page.title}</div>
                <div className="mt-0.5 max-w-5xl truncate text-xs text-muted-foreground">
                    {page.url}
                </div>
            </div>

            {strategy && hasRun && (
                <div
                    className="grid gap-3 rounded-lg bg-muted/30 p-4 md:grid-cols-4"
                    aria-label="Latest ETL execution strategy"
                >
                    <div>
                        <div className="text-xs text-muted-foreground">
                            Strategy
                        </div>
                        <div className="mt-1 text-sm font-medium">
                            {strategy.name}
                        </div>
                    </div>
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

            <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
                <Card className="xl:sticky xl:top-24">
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2 text-base">
                            <FileText className="h-4 w-4" />
                            Source Document
                        </CardTitle>
                        <CardDescription>
                            Cached page content used as the fixed input to this
                            review execution.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <pre className="max-h-[720px] overflow-auto rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap">
                            {mockSourceDocument(page.title, page.url)}
                        </pre>
                    </CardContent>
                </Card>

                <div className="space-y-4">
                    {artifacts.map((artifact, index) => (
                        <div key={artifact.label}>
                            {index > 0 && (
                                <div className="flex justify-center py-1">
                                    <ArrowDown
                                        className="h-5 w-5 text-muted-foreground"
                                        aria-hidden="true"
                                    />
                                </div>
                            )}
                            <Card>
                                <CardHeader>
                                    <CardTitle className="flex items-center gap-2 text-base">
                                        <FileCode2 className="h-4 w-4" />
                                        {artifact.label}
                                    </CardTitle>
                                    <CardDescription>
                                        {hasRun
                                            ? "Generated output ready for manual review."
                                            : "Run ETL to generate this stage artifact."}
                                    </CardDescription>
                                </CardHeader>
                                <CardContent>
                                    {hasRun ? (
                                        <pre className="max-h-[260px] overflow-auto rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap">
                                            {artifact.body}
                                        </pre>
                                    ) : (
                                        <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                                            No artifact generated yet.
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        </div>
                    ))}

                    <Card className="border-primary/30">
                        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                            <div>
                                <div className="font-medium">
                                    Ready to make this a Golden example?
                                </div>
                                <div className="mt-1 text-sm text-muted-foreground">
                                    Promote only after manually validating the
                                    source and all three generated outputs.
                                </div>
                            </div>
                            <Button
                                onClick={promoteGolden}
                                disabled={!hasRun || page.isGolden}
                            >
                                <Sparkles className="mr-2 h-4 w-4" />
                                {page.isGolden
                                    ? "Already Golden"
                                    : "Promote as Golden Sample"}
                            </Button>
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
