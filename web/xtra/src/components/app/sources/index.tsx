"use client";
import MuiBox from "@mui/material/Box";
import MuiTypography from "@mui/material/Typography";
import ResizableTable from "@/components/ui/resizable-table";

import { Button } from "@/components/ui/button";
import type { CrawlStatus, DiscoverStatus, Source } from "@/domain";
import {
    crawlRuns,
    getEffectiveCrawlRunId,
    getEffectiveDiscoveredPages,
    sources as sourceFixtures,
} from "@/mock-control-plane";
import {
    Box,
    Button as MuiButton,
    Chip,
    IconButton,
    Popover,
    Stack,
    TextField,
    Tooltip,
    Typography,
} from "@mui/material";
import type { TableColumnsType } from "antd";
import type { FilterDropdownProps } from "antd/es/table/interface";
import AlertTriangle from "@mui/icons-material/WarningAmber";
import CheckCircle2 from "@mui/icons-material/CheckCircle";
import Circle from "@mui/icons-material/RadioButtonUnchecked";
import Loader2 from "@mui/icons-material/Autorenew";
import Pencil from "@mui/icons-material/Edit";
import Plus from "@mui/icons-material/Add";
import Search from "@mui/icons-material/Search";
import Tags from "@mui/icons-material/LocalOffer";
import { useMemo, useState } from "react";
import Link from "@/components/ui/route-link";

function CrawlStatusCell({ status }: { status: CrawlStatus }) {
    const icon =
        status === "succeeded" ? (
            <CheckCircle2 className="h-3.5 w-3.5" />
        ) : status === "failed" ? (
            <AlertTriangle className="h-3.5 w-3.5" />
        ) : status === "running" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
            <Circle className="h-3.5 w-3.5" />
        );
    const color =
        status === "failed"
            ? "error"
            : status === "succeeded"
              ? "success"
              : "default";
    return (
        <Chip
            size="small"
            color={color}
            variant={
                status === "failed" || status === "succeeded"
                    ? "filled"
                    : "outlined"
            }
            icon={
                <Box component="span" sx={{ display: "inline-flex" }}>
                    {icon}
                </Box>
            }
            label={status.replace("_", " ")}
            sx={{ textTransform: "capitalize", fontWeight: 600 }}
        />
    );
}

function textFilterDropdown(placeholder: string) {
    function TextFilterDropdown({
        setSelectedKeys,
        selectedKeys,
        confirm,
        clearFilters,
        close,
    }: FilterDropdownProps) {
        return (
            <Box
                className="w-64 p-2"
                onKeyDown={(event) => event.stopPropagation()}
            >
                <TextField
                    autoFocus
                    fullWidth
                    size="small"
                    placeholder={placeholder}
                    value={(selectedKeys[0] as string) ?? ""}
                    onChange={(event) =>
                        setSelectedKeys(
                            event.target.value ? [event.target.value] : [],
                        )
                    }
                    onKeyDown={(event) => {
                        if (event.key === "Enter") confirm();
                    }}
                />
                <Box className="mt-2 flex justify-end gap-2">
                    <MuiButton
                        variant="text"
                        size="small"
                        onClick={() => {
                            clearFilters?.();
                            confirm();
                        }}
                    >
                        Reset
                    </MuiButton>
                    <MuiButton
                        variant="outlined"
                        size="small"
                        onClick={() => {
                            confirm();
                            close();
                        }}
                    >
                        Apply
                    </MuiButton>
                </Box>
            </Box>
        );
    }
    TextFilterDropdown.displayName = "TextFilterDropdown";
    return TextFilterDropdown;
}

function includesFilter(value: unknown, recordValue: unknown) {
    return String(recordValue ?? "")
        .toLowerCase()
        .includes(String(value).toLowerCase());
}

type SourceRow = Source & {
    effectiveDiscoveryStatus: DiscoverStatus;
    effectiveDiscoveredPages: number;
};

export default function Sources() {
    const [sourceRows, setSourceRows] = useState<Source[]>(sourceFixtures);
    const [quickSearch, setQuickSearch] = useState("");
    const [tagEditor, setTagEditor] = useState<{
        sourceId: string;
        anchorEl: HTMLElement;
    } | null>(null);
    const [tagDraft, setTagDraft] = useState("");

    // TODO(source-db): GET Sources, tags, latest crawl summary, discovery summary, and golden sample counts from the new PostgreSQL-backed Sources API.
    const derivedRows = useMemo<SourceRow[]>(
        () =>
            sourceRows.map((source) => {
                const effectiveRunId = getEffectiveCrawlRunId(source.id);
                const effectiveRun = crawlRuns.find(
                    (run) => run.id === effectiveRunId,
                );
                const effectivePages = getEffectiveDiscoveredPages(
                    source.id,
                ).filter(
                    (page) =>
                        !page.labels.includes("Ignore") &&
                        !page.labels.includes("Unclassified"),
                );
                return {
                    ...source,
                    effectiveDiscoveryStatus:
                        effectiveRun?.discoveryStatus ?? "not_started",
                    effectiveDiscoveredPages: effectivePages.length,
                };
            }),
        [sourceRows],
    );

    const rows = useMemo(
        () =>
            derivedRows.filter((source) => {
                const q = quickSearch.trim().toLowerCase();
                if (!q) return true;
                return [
                    source.name,
                    source.organizationName,
                    source.url,
                    source.tags.join(" "),
                    source.crawlStatus,
                    source.effectiveDiscoveryStatus,
                ].some((value) =>
                    String(value ?? "")
                        .toLowerCase()
                        .includes(q),
                );
            }),
        [derivedRows, quickSearch],
    );

    function openTagEditor(sourceId: string, anchorEl: HTMLElement) {
        setTagDraft("");
        setTagEditor({ sourceId, anchorEl });
    }

    function addTag() {
        if (!tagEditor) return;
        const tag = tagDraft.trim().toLowerCase();
        if (!tag) return;
        // TODO(source-db): Persist the Source/tag association in PostgreSQL.
        setSourceRows((current) =>
            current.map((source) =>
                source.id === tagEditor.sourceId && !source.tags.includes(tag)
                    ? { ...source, tags: [...source.tags, tag] }
                    : source,
            ),
        );
        setTagDraft("");
    }

    function removeTag(sourceId: string, tag: string) {
        // TODO(source-db): Delete the Source/tag association from PostgreSQL.
        setSourceRows((current) =>
            current.map((source) =>
                source.id === sourceId
                    ? {
                          ...source,
                          tags: source.tags.filter((item) => item !== tag),
                      }
                    : source,
            ),
        );
    }

    const crawlFilters = useMemo(
        () =>
            [...new Set(sourceRows.map((source) => source.crawlStatus))].map(
                (status) => ({ text: status.replace("_", " "), value: status }),
            ),
        [sourceRows],
    );
    const discoveryFilters = useMemo(
        () =>
            [
                ...new Set(
                    derivedRows.map(
                        (source) => source.effectiveDiscoveryStatus,
                    ),
                ),
            ].map((status) => ({
                text: status.replace("_", " "),
                value: status,
            })),
        [derivedRows],
    );

    const columns: TableColumnsType<SourceRow> = [
        {
            title: "Source",
            dataIndex: "name",
            key: "name",
            width: 190,
            sorter: {
                compare: (a, b) => a.name.localeCompare(b.name),
                multiple: 6,
            },
            filterDropdown: textFilterDropdown("Search source"),
            filterIcon: (filtered) => (
                <Search
                    sx={{ fontSize: "1rem" }}
                    className={filtered ? "text-primary" : undefined}
                />
            ),
            onFilter: (value, record) => includesFilter(value, record.name),
            render: (value, record) => (
                <Link
                    className="font-medium hover:underline"
                    href={`/sources/${record.id}`}
                    style={{ color: "var(--ce-link)" }}
                >
                    {value}
                </Link>
            ),
        },
        {
            title: "Organization",
            dataIndex: "organizationName",
            key: "organizationName",
            width: 170,
            sorter: {
                compare: (a, b) =>
                    a.organizationName.localeCompare(b.organizationName),
                multiple: 5,
            },
            filterDropdown: textFilterDropdown("Search organization"),
            filterIcon: (filtered) => (
                <Search
                    sx={{ fontSize: "1rem" }}
                    className={filtered ? "text-primary" : undefined}
                />
            ),
            onFilter: (value, record) =>
                includesFilter(value, record.organizationName),
        },
        {
            title: "URL",
            dataIndex: "url",
            key: "url",
            ellipsis: true,
            sorter: {
                compare: (a, b) => a.url.localeCompare(b.url),
                multiple: 4,
            },
            filterDropdown: textFilterDropdown("Search URL"),
            filterIcon: (filtered) => (
                <Search
                    sx={{ fontSize: "1rem" }}
                    className={filtered ? "text-primary" : undefined}
                />
            ),
            onFilter: (value, record) => includesFilter(value, record.url),
            render: (value) => (
                <Tooltip title={value} placement="top">
                    <a
                        href={value}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm text-muted-foreground hover:underline"
                        onClick={(event) => event.stopPropagation()}
                    >
                        {value}
                    </a>
                </Tooltip>
            ),
        },
        {
            title: "Tags",
            key: "tags",
            width: 190,
            sorter: {
                compare: (a, b) =>
                    a.tags.join(",").localeCompare(b.tags.join(",")),
                multiple: 3,
            },
            filterDropdown: textFilterDropdown("Search tags"),
            filterIcon: (filtered) => (
                <Search
                    sx={{ fontSize: "1rem" }}
                    className={filtered ? "text-primary" : undefined}
                />
            ),
            onFilter: (value, record) =>
                includesFilter(value, record.tags.join(" ")),
            render: (_, record) => (
                <Stack
                    direction="row"
                    spacing={0.75}
                    sx={{ minWidth: 0, alignItems: "center" }}
                >
                    {record.tags.slice(0, 2).map((tag) => (
                        <Chip
                            key={tag}
                            label={tag}
                            size="small"
                            variant="outlined"
                        />
                    ))}
                    {record.tags.length > 2 && (
                        <Chip
                            label={`+${record.tags.length - 2}`}
                            size="small"
                            variant="outlined"
                        />
                    )}
                    <Tooltip title="Edit tags">
                        <IconButton
                            size="small"
                            aria-label={`Edit tags for ${record.name}`}
                            onClick={(event) => {
                                event.stopPropagation();
                                openTagEditor(record.id, event.currentTarget);
                            }}
                        >
                            <Tags sx={{ fontSize: "1rem" }} />
                        </IconButton>
                    </Tooltip>
                </Stack>
            ),
        },
        {
            title: "Crawl",
            dataIndex: "crawlStatus",
            key: "crawlStatus",
            width: 115,
            sorter: {
                compare: (a, b) => a.crawlStatus.localeCompare(b.crawlStatus),
                multiple: 2,
            },
            filters: crawlFilters,
            filterMultiple: true,
            onFilter: (value, record) => record.crawlStatus === value,
            render: (value) => (
                <CrawlStatusCell status={value as CrawlStatus} />
            ),
        },
        {
            title: "Actions",
            key: "actions",
            width: 150,
            render: (_, record) => (
                <Stack
                    direction="row"
                    spacing={0.5}
                    sx={{ justifyContent: "flex-end", alignItems: "center" }}
                >
                    <Button size="sm" variant="ghost" asChild>
                        <Link href={`/sources/${record.id}`}>Crawls</Link>
                    </Button>
                    <Tooltip title="Edit source">
                        <Link href={`/sources/${record.id}/edit`}>
                            <IconButton
                                size="small"
                                aria-label={`Edit ${record.name}`}
                            >
                                <Pencil sx={{ fontSize: "1.0625rem" }} />
                            </IconButton>
                        </Link>
                    </Tooltip>
                </Stack>
            ),
        },
        {
            title: "Discovery",
            dataIndex: "effectiveDiscoveryStatus",
            key: "effectiveDiscoveryStatus",
            width: 115,
            sorter: {
                compare: (a, b) =>
                    a.effectiveDiscoveryStatus.localeCompare(
                        b.effectiveDiscoveryStatus,
                    ),
                multiple: 1,
            },
            filters: discoveryFilters,
            filterMultiple: true,
            onFilter: (value, record) =>
                record.effectiveDiscoveryStatus === value,
            render: (value) => (
                <Chip
                    size="small"
                    variant="outlined"
                    label={String(value).replace("_", " ")}
                    sx={{ textTransform: "capitalize" }}
                />
            ),
            hidden: true,
        },
        {
            title: "Pages",
            dataIndex: "lastCrawlPages",
            key: "lastCrawlPages",
            width: 100,
            sorter: {
                compare: (a, b) =>
                    (a.lastCrawlPages ?? 0) - (b.lastCrawlPages ?? 0),
                multiple: 1,
            },
            hidden: true,
        },
        {
            title: "Useful pages",
            dataIndex: "effectiveDiscoveredPages",
            key: "effectiveDiscoveredPages",
            width: 120,
            sorter: {
                compare: (a, b) =>
                    a.effectiveDiscoveredPages - b.effectiveDiscoveredPages,
                multiple: 1,
            },
            hidden: true,
        },
        {
            title: "Golden",
            dataIndex: "goldenSamples",
            key: "goldenSamples",
            width: 100,
            sorter: {
                compare: (a, b) => a.goldenSamples - b.goldenSamples,
                multiple: 1,
            },
            hidden: true,
        },
    ];

    const editingSource = tagEditor
        ? sourceRows.find((source) => source.id === tagEditor.sourceId)
        : undefined;

    return (
        <Box className="space-y-6">
            <Box className="flex flex-wrap items-start justify-between gap-4">
                <Box>
                    <MuiTypography
                        variant="h1"
                        component="h1"
                        className="text-2xl font-semibold"
                    >
                        All Sources
                    </MuiTypography>
                    <MuiTypography
                        component="p"
                        className="mt-1 text-sm text-muted-foreground"
                    >
                        Add a Source, open it to manage its crawl runs, then
                        open a completed crawl when you are ready to run
                        discovery.
                    </MuiTypography>
                </Box>
                <Button asChild>
                    <Link href="/sources/new">
                        <Plus className="mr-2 h-4 w-4" />
                        Add source
                    </Link>
                </Button>
            </Box>

            <MuiBox
                component="section"
                aria-label="Sources table"
                className="space-y-2"
            >
                <Box
                    sx={{
                        py: 1,
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                    }}
                >
                    <Search sx={{ fontSize: "1.0625rem" }} />
                    <TextField
                        variant="standard"
                        fullWidth
                        placeholder="Search sources…"
                        value={quickSearch}
                        onChange={(event) => setQuickSearch(event.target.value)}
                        slotProps={{ input: { disableUnderline: true } }}
                        sx={{ maxWidth: 460 }}
                    />
                    <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{
                            ml: "auto",
                            whiteSpace: "nowrap",
                            color: "text.secondary",
                        }}
                    >
                        Use column headers to filter/sort; use Columns to show
                        or hide fields.
                    </Typography>
                </Box>
                <ResizableTable<SourceRow>
                    ariaLabel="Sources"
                    rowKey="id"
                    columns={columns}
                    dataSource={rows}
                    size="middle"
                    tableLayout="fixed"
                    pagination={{
                        defaultPageSize: 25,
                        showSizeChanger: true,
                        pageSizeOptions: [10, 25, 50, 100],
                        showTotal: (total) => `${total} sources`,
                    }}
                />
            </MuiBox>

            <Popover
                disableScrollLock
                open={Boolean(tagEditor)}
                anchorEl={tagEditor?.anchorEl ?? null}
                onClose={() => setTagEditor(null)}
                anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
            >
                <Box sx={{ p: 2, width: 320 }}>
                    <Typography variant="subtitle2">Tags</Typography>
                    <Typography variant="caption" color="text.secondary">
                        {editingSource?.name}
                    </Typography>
                    <Stack
                        direction="row"
                        spacing={0.75}
                        sx={{ mt: 1.5, mb: 1.5, flexWrap: "wrap" }}
                    >
                        {editingSource?.tags.length ? (
                            editingSource.tags.map((tag) => (
                                <Chip
                                    key={tag}
                                    label={tag}
                                    size="small"
                                    onDelete={() =>
                                        removeTag(editingSource.id, tag)
                                    }
                                />
                            ))
                        ) : (
                            <Typography variant="body2" color="text.secondary">
                                No tags yet.
                            </Typography>
                        )}
                    </Stack>
                    <Stack direction="row" spacing={1}>
                        <TextField
                            size="small"
                            fullWidth
                            placeholder="Add a tag"
                            value={tagDraft}
                            onChange={(event) =>
                                setTagDraft(event.target.value)
                            }
                            onKeyDown={(event) => {
                                if (event.key === "Enter") {
                                    event.preventDefault();
                                    addTag();
                                }
                            }}
                        />
                        <Button size="sm" variant="outline" onClick={addTag}>
                            Add
                        </Button>
                    </Stack>
                </Box>
            </Popover>
        </Box>
    );
}
