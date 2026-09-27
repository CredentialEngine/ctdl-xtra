import { resourceFromAttributes } from "@opentelemetry/resources";
import { ATTR_SERVICE_NAME } from "@opentelemetry/semantic-conventions";
import "server-only";

export async function register() {
    if (process.env.NEXT_RUNTIME !== "nodejs") {
        return;
    }

    const connectionString =
        process.env.APPLICATIONINSIGHTS_CONNECTION_STRING ??
        process.env.NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING;

    const cloudRoleName =
        process.env.APPLICATION_INSIGHTS_CLOUD_ROLE_NAME ??
        process.env.NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME;

    if (process.env.NEXT_PUBLIC_NODE_ENV === "development") {
        return; // No Logs for local
    }

    if (!connectionString) {
        throw new Error(
            "[instrumentation] NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING is not set. " +
                "This is required in all deployed environments.",
        );
    }
    if (!cloudRoleName) {
        throw new Error(
            "[instrumentation] NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME is not set. " +
                "This is required in all deployed environments.",
        );
    }

    const { useAzureMonitor: configureAzureMonitor } =
        await import("@azure/monitor-opentelemetry");

    configureAzureMonitor({
        azureMonitorExporterOptions: {
            connectionString,
        },
        resource: resourceFromAttributes({
            [ATTR_SERVICE_NAME]: cloudRoleName,
        }),
    });
}
