import MuiTypography from "@mui/material/Typography";
import { Box } from "@mui/material";
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
import { useSnackbar } from "@/components/ui/snackbar-provider";
import { sources, organizations } from "@/mock-control-plane";
import { useState } from "react";
import Link from "@/components/ui/route-link";
import { useParams } from "next/navigation";

export default function EditSource() {
    const { sourceId } = useParams<{ sourceId: string }>();
    const existing = sources.find((c) => c.id === sourceId);
    const { showSnackbar } = useSnackbar();
    const [organizationId, setOrganizationId] = useState(
        existing?.organizationId ?? "",
    );
    const [name, setName] = useState(existing?.name ?? "");
    const [url, setUrl] = useState(existing?.url ?? "");
    const [tags, setTags] = useState(existing?.tags.join(", ") ?? "");
    if (!existing) return <Box>Source not found.</Box>;
    function save() {
        /* TODO(source-db): PATCH the new PostgreSQL source row, including normalized tags. */ showSnackbar(
            { title: "Source update endpoint not connected" },
        );
    }
    function remove() {
        /* TODO(source-db): DELETE/archive the new PostgreSQL source row after checking active runs. */ showSnackbar(
            { title: "Source delete endpoint not connected" },
        );
    }
    return (
        <Box className="mx-auto max-w-2xl space-y-6">
            <Box>
                <MuiTypography
                    variant="h1"
                    component="h1"
                    className="text-2xl font-semibold"
                >
                    Edit source
                </MuiTypography>
                <MuiTypography
                    component="p"
                    className="mt-1 text-sm text-muted-foreground"
                >
                    Update the website or organization association.
                </MuiTypography>
            </Box>
            <Card>
                <CardHeader>
                    <CardTitle>{existing.name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-5">
                    <Box className="space-y-2">
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
                    </Box>
                    <Box className="space-y-2">
                        <Label>Name</Label>
                        <Input
                            value={name}
                            onChange={(e) => setName(e.target.value)}
                        />
                    </Box>
                    <Box className="space-y-2">
                        <Label>Website URL</Label>
                        <Input
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                        />
                    </Box>
                    <Box className="space-y-2">
                        <Label>Tags</Label>
                        <Input
                            value={tags}
                            onChange={(e) => setTags(e.target.value)}
                            placeholder="higher-ed, courses, pilot"
                        />
                        <MuiTypography
                            component="p"
                            className="text-xs text-muted-foreground"
                        >
                            Enter comma-separated tags.
                        </MuiTypography>
                    </Box>
                    <Box className="flex justify-between">
                        <Button variant="destructive" onClick={remove}>
                            Delete source
                        </Button>
                        <Box className="flex gap-2">
                            <Button variant="outline" asChild>
                                <Link href={`/sources/${sourceId}`}>
                                    Cancel
                                </Link>
                            </Button>
                            <Button onClick={save}>Save changes</Button>
                        </Box>
                    </Box>
                </CardContent>
            </Card>
        </Box>
    );
}
