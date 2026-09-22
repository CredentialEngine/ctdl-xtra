import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
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
import { useSnackbar } from "@/components/ui/snackbar-provider";
import {
    benchmarkStrategies,
    discoveredPages,
    extractStrategies,
    publishStrategies,
    sources,
    transformStrategies,
} from "@/mock-control-plane";
import ArrowDown from "@mui/icons-material/ArrowDownward";
import FileCode2 from "@mui/icons-material/DataObject";
import FileText from "@mui/icons-material/Description";
import Sparkles from "@mui/icons-material/AutoAwesome";
import Link from "@/components/ui/route-link";
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
    const { showSnackbar } = useSnackbar();
    // TODO(source-db): GET the cached source-document artifact for this discovered page/crawl snapshot.
    // TODO(benchmark-db): GET prior single-page ETL executions, select the requested/latest execution, and load any Golden Sample record.
    const source = sources.find((item) => item.id === sourceId);
    const page = discoveredPages.find(
        (item) => item.id === pageId && item.sourceId === sourceId,
    );
    const strategy = benchmarkStrategies.find(
        (item) => item.status === "active",
    );

    if (!source || !page) return <Box>Discovered page not found.</Box>;

    const hasRun =
        page.validationStatus === "ready_for_review" || page.isGolden;

    function promoteGolden() {
        // TODO(benchmark-db): Persist the source document, exact Strategy snapshot, and manually approved Extract/Transform/Publish-ready outputs as a Promoted Golden Sample for this Source.
        showSnackbar({
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
        <Box className="space-y-6">
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

            <Box className="flex flex-wrap items-end justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        {source.name}
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        {source.url}
                    </MuiTypography>
                </Box>
                <Button asChild>
                    <Link
                        href={`/benchmarks/workspaces/${source.id}/pages/${page.id}/run`}
                    >
                        Run again
                    </Link>
                </Button>
            </Box>

            <Box className="rounded-lg bg-muted/35 p-4">
                <Box className="flex flex-wrap items-center gap-2">
                    <MuiTypography
                        component="span"
                        className="text-xs font-medium uppercase tracking-wide text-muted-foreground"
                    >
                        Page under review
                    </MuiTypography>
                    <Box className="flex flex-wrap gap-1">
                        {page.labels.map((label) => (
                            <Badge key={label} variant="outline">
                                {label}
                            </Badge>
                        ))}
                    </Box>
                    {page.isGolden && <Badge>Promoted Golden</Badge>}
                </Box>
                <Box className="mt-1 font-semibold">{page.title}</Box>
                <Box className="mt-0.5 max-w-5xl truncate text-xs text-muted-foreground">
                    {page.url}
                </Box>
            </Box>

            {strategy && hasRun && (
                <Box
                    className="grid gap-3 rounded-lg bg-muted/30 p-4 md:grid-cols-4"
                    aria-label="Latest ETL execution strategy"
                >
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Strategy
                        </Box>
                        <Box className="mt-1 text-sm font-medium">
                            {strategy.name}
                        </Box>
                    </Box>
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Extract
                        </Box>
                        <Box className="mt-1 text-sm font-medium">
                            {optionName(
                                extractStrategies,
                                strategy.extractOptionId,
                            )}
                        </Box>
                    </Box>
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Transform
                        </Box>
                        <Box className="mt-1 text-sm font-medium">
                            {optionName(
                                transformStrategies,
                                strategy.transformOptionId,
                            )}
                        </Box>
                    </Box>
                    <Box>
                        <Box className="text-xs text-muted-foreground">
                            Publish-ready
                        </Box>
                        <Box className="mt-1 text-sm font-medium">
                            {optionName(
                                publishStrategies,
                                strategy.publishReadyOptionId,
                            )}
                        </Box>
                    </Box>
                </Box>
            )}

            <Box className="grid gap-6 xl:grid-cols-2 xl:items-start">
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
                        <MuiBox
                            component="pre"
                            className="max-h-[720px] overflow-auto rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap"
                        >
                            {mockSourceDocument(page.title, page.url)}
                        </MuiBox>
                    </CardContent>
                </Card>

                <Box className="space-y-4">
                    {artifacts.map((artifact, index) => (
                        <Box key={artifact.label}>
                            {index > 0 && (
                                <Box className="flex justify-center py-1">
                                    <ArrowDown
                                        className="h-5 w-5 text-muted-foreground"
                                        aria-hidden="true"
                                    />
                                </Box>
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
                                        <MuiBox
                                            component="pre"
                                            className="max-h-[260px] overflow-auto rounded-md bg-muted p-4 text-xs leading-relaxed whitespace-pre-wrap"
                                        >
                                            {artifact.body}
                                        </MuiBox>
                                    ) : (
                                        <Box className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                                            No artifact generated yet.
                                        </Box>
                                    )}
                                </CardContent>
                            </Card>
                        </Box>
                    ))}

                    <Card className="border-primary/30">
                        <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                            <Box>
                                <Box className="font-medium">
                                    Ready to make this a Golden example?
                                </Box>
                                <Box className="mt-1 text-sm text-muted-foreground">
                                    Promote only after manually validating the
                                    source and all three generated outputs.
                                </Box>
                            </Box>
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
                </Box>
            </Box>
        </Box>
    );
}
