"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useXtraAuth } from "../app/components/auth/AuthProvider";
import { Dashboard } from "@/components/app/dashboard";
import { AppLoadingScreen } from "@/components/ui/loading-state";
import { useSnackbar } from "@/components/ui/snackbar-provider";

const SESSION_KEEPALIVE_MS = 2 * 60 * 1000;

function pageTitle(pathname: string) {
    if (pathname === "/") return "Home";
    if (pathname === "/profile") return "Profile";
    if (pathname === "/about") return "About";
    if (pathname === "/logout") return "Sign Out";

    if (pathname === "/sources/new") return "New Source";
    if (/^\/sources\/[^/]+\/edit$/.test(pathname)) return "Edit Source";
    if (/^\/sources\/[^/]+$/.test(pathname)) return "Source";
    if (pathname === "/sources/all") return "All Sources";
    if (pathname === "/sources") return "Sources";

    if (pathname === "/crawls/new") return "New Crawl";
    if (/^\/crawls\/[^/]+\/discovery$/.test(pathname)) return "Discovery";
    if (/^\/crawls\/[^/]+$/.test(pathname)) return "Crawl";
    if (pathname === "/crawls") return "Crawls";

    if (pathname === "/benchmarks/strategies") return "Benchmark Strategies";
    if (pathname === "/benchmarks/runs/new") return "New Benchmark Run";
    if (/^\/benchmarks\/runs\/[^/]+\/samples\/[^/]+$/.test(pathname)) {
        return "Benchmark Sample";
    }
    if (/^\/benchmarks\/runs\/[^/]+$/.test(pathname)) return "Benchmark Run";
    if (pathname === "/benchmarks/runs") return "Benchmark Runs";
    if (/^\/benchmarks\/workspaces\/[^/]+\/golden$/.test(pathname)) {
        return "Golden Samples";
    }
    if (/^\/benchmarks\/workspaces\/[^/]+\/pages\/[^/]+\/run$/.test(pathname)) {
        return "Run Page Benchmark";
    }
    if (/^\/benchmarks\/workspaces\/[^/]+\/pages\/[^/]+$/.test(pathname)) {
        return "Benchmark Page";
    }
    if (/^\/benchmarks\/workspaces\/[^/]+$/.test(pathname)) {
        return "Benchmark Workspace";
    }
    if (pathname === "/benchmarks/workspaces") return "Benchmark Workspaces";
    if (pathname === "/benchmarks") return "Benchmarks";

    if (pathname === "/publishing/runs") return "ETL Runs";
    if (pathname === "/publishing/new") return "New Publishing Run";
    if (/^\/publishing\/[^/]+$/.test(pathname)) return "Publishing Run";
    if (pathname === "/publishing") return "Publishing";

    return "CTDL xTRA";
}

export default function ClientApp({
    children,
}: Readonly<{ children: ReactNode }>) {
    const { user, isLoading, refresh } = useXtraAuth();
    const pathname = usePathname();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { showSnackbar } = useSnackbar();

    useEffect(() => {
        const title = pageTitle(pathname);
        document.title = title === "CTDL xTRA" ? title : `${title} | CTDL xTRA`;
    }, [pathname]);

    useEffect(() => {
        if (!user) return;

        const keepAlive = window.setInterval(() => {
            void refresh();
        }, SESSION_KEEPALIVE_MS);

        return () => window.clearInterval(keepAlive);
    }, [refresh, user]);

    useEffect(() => {
        if (isLoading || user) return;

        if (
            pathname !== "/" &&
            pathname !== "/about" &&
            pathname !== "/logout"
        ) {
            router.replace("/?auth=required");
            return;
        }

        if (searchParams.get("auth") === "required") {
            showSnackbar({
                title: "You are not authenticated. Please log in to access this page.",
                severity: "info",
            });
            window.history.replaceState(null, "", "/");
        }
    }, [isLoading, pathname, router, searchParams, showSnackbar, user]);

    if (isLoading) return <AppLoadingScreen label="Loading your session" />;
    if (
        !user &&
        pathname !== "/" &&
        pathname !== "/about" &&
        pathname !== "/logout"
    ) {
        return null;
    }

    return <Dashboard>{children}</Dashboard>;
}
