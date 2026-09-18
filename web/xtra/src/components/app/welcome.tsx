import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { ArrowRight, Database, FlaskConical, Globe2, Send } from "lucide-react";
import Link from "next/link";

export default function Welcome() {
    return (
        <div className="space-y-8">
            <div className="max-w-3xl">
                <h1 className="text-3xl font-semibold tracking-tight">
                    CTDL xTRA pipeline control plane
                </h1>
                <p className="mt-3 text-muted-foreground">
                    Manage public website sources, crawl and discover useful
                    pages, prove pipeline correctness with golden benchmarks,
                    and publish complete sources to projects.
                </p>
            </div>
            <div className="grid gap-4 lg:grid-cols-3">
                <Card>
                    <CardHeader>
                        <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                            <Globe2 className="h-5 w-5" />
                        </div>
                        <CardTitle>Sources</CardTitle>
                        <CardDescription>
                            Associate website URLs with organizations, manually
                            crawl them, then discover and label useful pages.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button variant="outline" asChild>
                            <Link href="/sources">
                                Manage sources
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                            <FlaskConical className="h-5 w-5" />
                        </div>
                        <CardTitle>Benchmarks</CardTitle>
                        <CardDescription>
                            Validate selected discovered pages, promote approved
                            examples to golden, and audit source-wide benchmark
                            runs.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button variant="outline" asChild>
                            <Link href="/benchmarks">
                                Open benchmarks
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader>
                        <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                            <Send className="h-5 w-5" />
                        </div>
                        <CardTitle>Publishing</CardTitle>
                        <CardDescription>
                            Pick strategies and run the pipeline across every
                            publishable discovered page in a source.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button variant="outline" asChild>
                            <Link href="/publishing">
                                Publish source
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                    </CardContent>
                </Card>
            </div>
            <Card>
                <CardContent className="flex items-start gap-3 p-5">
                    <Database className="mt-0.5 h-5 w-5 text-muted-foreground" />
                    <div>
                        <div className="font-medium">Integration-ready UI</div>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Sources, crawl runs, benchmarks, and publishing
                            workflows are separated so backend services can be
                            connected independently.
                        </p>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
