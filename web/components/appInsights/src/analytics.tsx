"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { initializeAppInsights } from "./appInsights";

type AnalyticsProps = {
    connectionString: string;
    roleName: string;
};

export function Analytics({ connectionString, roleName }: AnalyticsProps) {
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const queryString = searchParams.toString();

    useEffect(() => {
        if (!connectionString || !roleName) {
            return;
        }

        const appInsights = initializeAppInsights(connectionString, roleName);

        if (!appInsights) {
            return;
        }

        appInsights.trackPageView({
            name: pathname,
            uri: globalThis.window.location.href,
            properties: {
                path: pathname,
                queryString,
                source: "next-app-router",
            },
        });
    }, [connectionString, pathname, queryString, roleName]);

    return null;
}
