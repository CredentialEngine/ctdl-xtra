"use client";

import {
    Box,
    CircularProgress,
    Skeleton,
    Stack,
    Typography,
} from "@mui/material";

export function AppLoadingScreen({
    label = "Loading xTRA",
}: {
    label?: string;
}) {
    return (
        <Box
            role="status"
            aria-live="polite"
            aria-label={label}
            sx={{
                minHeight: "100vh",
                display: "grid",
                placeItems: "center",
                bgcolor: "background.default",
                color: "text.primary",
                p: 3,
            }}
        >
            <Stack spacing={2} sx={{ alignItems: "center" }}>
                <CircularProgress size={36} />
                <Typography variant="body2" color="text.secondary">
                    {label}
                </Typography>
            </Stack>
        </Box>
    );
}

export function PageLoadingSkeleton() {
    return (
        <Box
            role="status"
            aria-live="polite"
            aria-label="Loading page"
            sx={{ width: "100%", p: { xs: 2, md: 3 } }}
        >
            <Stack spacing={2.5}>
                <Box>
                    <Skeleton variant="text" width="32%" height={44} />
                    <Skeleton variant="text" width="58%" height={24} />
                </Box>
                <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
                    <Skeleton variant="rounded" height={88} sx={{ flex: 1 }} />
                    <Skeleton variant="rounded" height={88} sx={{ flex: 1 }} />
                    <Skeleton variant="rounded" height={88} sx={{ flex: 1 }} />
                </Stack>
                <Skeleton variant="rounded" height={52} />
                <Skeleton variant="rounded" height={380} />
            </Stack>
        </Box>
    );
}
