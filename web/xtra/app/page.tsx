"use client";

import Welcome from "@/components/app/welcome";
import { Alert, Box } from "@mui/material";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function HomePageContent() {
    const searchParams = useSearchParams();
    const sessionExpired = searchParams.get("sessionExpired") === "1";
    return (
        <Box className="space-y-6">
            {sessionExpired && (
                <Alert severity="info">
                    Your session expired, so you were signed out and returned to
                    the home page. Please log in again to continue.
                </Alert>
            )}

            <Welcome />
        </Box>
    );
}

export default function HomePage() {
    return (
        <Suspense fallback={null}>
            <HomePageContent />
        </Suspense>
    );
}
