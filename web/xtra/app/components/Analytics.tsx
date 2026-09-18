"use client";

import { Analytics } from "@credentialengine/app-insights";
import { useConfigContext } from "./providers/ConfigProvider";

export function AnalyticsWithConfig() {
    const {
        NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING,
        NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME,
    } = useConfigContext();

    return (
        <Analytics
            connectionString={
                NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING
            }
            roleName={NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME}
        />
    );
}
