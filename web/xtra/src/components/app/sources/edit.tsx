import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { sources, organizations } from "@/mock-control-plane";
import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

export default function EditSource() {
    const { sourceId } = useParams<{ sourceId: string }>();
    const existing = sources.find((c) => c.id === sourceId);
    const { toast } = useToast();
    const [organizationId, setOrganizationId] = useState(
        existing?.organizationId ?? "",
    );
    const [name, setName] = useState(existing?.name ?? "");
    const [url, setUrl] = useState(existing?.url ?? "");
    const [tags, setTags] = useState(existing?.tags.join(", ") ?? "");
    if (!existing) return <div>Source not found.</div>;
    function save() {
        /* TODO(source-db): PATCH the new PostgreSQL source row, including normalized tags. */ toast(
            { title: "Source update endpoint not connected" },
        );
    }
    function remove() {
        /* TODO(source-db): DELETE/archive the new PostgreSQL source row after checking active runs. */ toast(
            { title: "Source delete endpoint not connected" },
        );
    }
    return (
        <div className="mx-auto max-w-2xl space-y-6">
            <div>
                <h1 className="text-2xl font-semibold">Edit source</h1>
                <p className="mt-1 text-sm text-muted-foreground">
                    Update the website or organization association.
                </p>
            </div>
            <Card>
                <CardHeader>
                    <CardTitle>{existing.name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                    <div className="space-y-2">
                        <Label>Organization</Label>
                        <Select
                            value={organizationId}
                            onValueChange={setOrganizationId}
                        >
                            <SelectTrigger>
                                <SelectValue />
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
                        <Label>Name</Label>
                        <Input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Website URL</Label>
                        <Input
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                        />
                    </div>
                    <div className="space-y-2">
                        <Label>Tags</Label>
                        <Input
                            value={tags}
                            onChange={(e) => setTags(e.target.value)}
                            placeholder="higher-ed, courses, pilot"
                        />
                        <p className="text-xs text-muted-foreground">
                            Enter comma-separated tags.
                        </p>
                    </div>
                    <div className="flex justify-between">
                        <Button variant="destructive" onClick={remove}>
                            Delete source
                        </Button>
                        <div className="flex gap-2">
                            <Button variant="outline" asChild>
                                <Link href={`/sources/${sourceId}`}>
                                    Cancel
                                </Link>
                            </Button>
                            <Button onClick={save}>Save changes</Button>
                        </div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
