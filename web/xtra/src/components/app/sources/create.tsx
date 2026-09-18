import BreadcrumbTrail from "@/components/ui/breadcrumb-trail";
import { Button } from "@/components/ui/button";
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { organizations } from "@/mock-control-plane";
import { useState } from "react";
import Link from "next/link";

export default function CreateSource() {
    const { toast } = useToast();
    const [organizationId, setOrganizationId] = useState("");
    const [name, setName] = useState("");
    const [url, setUrl] = useState("");
    const [tags, setTags] = useState("");
    // TODO(accounts-api): Load organization ids + names from Credential Engine Accounts instead of fixtures.

    function save() {
        // TODO(source-db): POST { organizationId, name, url, tags } to the source API and INSERT it into the new PostgreSQL source table.
        // TODO(source-api): Validate URL uniqueness/canonicalization and return the newly-created source id.
        toast({
            title: "Source database not connected",
            description:
                "The form is ready for the new PostgreSQL-backed source endpoint.",
        });
    }

    return (
        <div className="mx-auto max-w-2xl space-y-6">
            <BreadcrumbTrail
                items={[
                    { label: "Sources", href: "/sources" },
                    { label: "Add source", href: "/sources/new" },
                ]}
            />
            <div>
                <h1 className="text-2xl font-semibold">Add source</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    A source is a public website URL associated with an
                    organization.
                </p>
            </div>
            <Card>
                <CardHeader>
                    <CardTitle>Source details</CardTitle>
                    <CardDescription>
                        Crawling does not start automatically after creation.
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-5">
                    <div className="space-y-2">
                        <Label>Organization</Label>
                        <Select
                            value={organizationId}
                            onValueChange={setOrganizationId}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder="Choose an organization" />
                            </SelectTrigger>
                            <SelectContent>
                                {organizations.map((o) => (
                                    <SelectItem key={o.id} value={o.id}>
                                        {o.name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="name">Source name</Label>
                        <Input
                            id="name"
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                            placeholder="2026 Academic Source"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="url">Website URL</Label>
                        <Input
                            id="url"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="https://source.example.edu"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label htmlFor="tags">Tags</Label>
                        <Input
                            id="tags"
                            value={tags}
                            onChange={(e) => setTags(e.target.value)}
                            placeholder="higher-ed, courses, pilot"
                        />
                        <p className="text-xs text-muted-foreground">
                            Enter comma-separated tags.
                        </p>
                    </div>
                    <div className="flex justify-end gap-2">
                        <Button variant="outline" asChild>
                            <Link href="/sources">Cancel</Link>
                        </Button>
                        <Button
                            onClick={save}
                            disabled={!organizationId || !name || !url}
                        >
                            Create source
                        </Button>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
