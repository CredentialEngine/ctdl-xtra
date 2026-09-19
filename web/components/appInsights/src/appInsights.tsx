"use client";

import { ClickAnalyticsPlugin } from "@microsoft/applicationinsights-clickanalytics-js";
import { ReactPlugin } from "@microsoft/applicationinsights-react-js";
import {
    ApplicationInsights,
    ITelemetryItem,
} from "@microsoft/applicationinsights-web";

export type TelemetrySeverity =
    "verbose" | "information" | "warning" | "error" | "critical";

export type TraceTelemetryOptions = {
    message: string;
    severity?: TelemetrySeverity;
    properties?: Record<string, unknown>;
    measurements?: Record<string, number>;
};

let appInsightsInstance: ApplicationInsights | undefined;
let activeConnectionString: string | undefined;
let reactPluginInstance: ReactPlugin | undefined;
let clickPluginInstance: ClickAnalyticsPlugin | undefined;
let hasTrackedInitialization = false;

const clickPluginConfig = {
    autoCapture: true,
    dataTags: {
        useDefaultContentNameOrId: true,
    },
};

const getSeverityLevel = (severity: TelemetrySeverity = "information") => {
    switch (severity) {
        case "verbose":
            return 0;
        case "information":
            return 1;
        case "warning":
            return 2;
        case "error":
            return 3;
        case "critical":
            return 4;
        default:
            return 1;
    }
};

const stringifyTelemetryValue = (value: unknown) => {
    if (value instanceof Error) {
        return `${value.name}: ${value.message}`;
    }

    if (typeof value === "string") {
        return value;
    }

    if (
        typeof value === "number" ||
        typeof value === "boolean" ||
        typeof value === "bigint"
    ) {
        return String(value);
    }

    if (value instanceof Date) {
        return value.toISOString();
    }

    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
};

const sanitizeProperties = (properties?: Record<string, unknown>) =>
    Object.fromEntries(
        Object.entries(properties ?? {})
            .filter(([, value]) => value !== undefined && value !== null)
            .map(([key, value]) => [key, stringifyTelemetryValue(value)]),
    );

const sanitizeMeasurements = (measurements?: Record<string, number>) =>
    Object.fromEntries(
        Object.entries(measurements ?? {}).filter(([, value]) =>
            Number.isFinite(value),
        ),
    );

const getExperimentsConfig = (): Record<string, unknown> => {
    try {
        const configJson =
            globalThis.window.localStorage.getItem("experiments");

        return configJson
            ? (JSON.parse(configJson) as Record<string, unknown>)
            : {};
    } catch (error) {
        console.error("Failed to retrieve experiments config:", error);
        return {};
    }
};

const experimentsConfigInitializer = (envelope: ITelemetryItem) => {
    if (!envelope.baseData) {
        return;
    }

    const config = getExperimentsConfig();
    envelope.baseData.properties = envelope.baseData.properties || {};
    envelope.baseData.properties.ExperimentsConfig = JSON.stringify(
        Object.keys(config).filter((key) => Boolean(config[key])),
    );
};

export const initializeAppInsights = (
    connectionString: string,
    roleName: string,
) => {
    if (!connectionString) {
        if (process.env.NEXT_PUBLIC_NODE_ENV === "development") {
            console.warn(
                "Application Insights was not initialized because no connection string was provided.",
            );
        }

        return undefined;
    }

    if (appInsightsInstance && activeConnectionString === connectionString) {
        return appInsightsInstance;
    }

    const reactPlugin = new ReactPlugin();
    const clickPlugin = new ClickAnalyticsPlugin();

    const appInsights = new ApplicationInsights({
        config: {
            connectionString,
            enableAjaxPerfTracking: true,
            enableCorsCorrelation: true,
            enableRequestHeaderTracking: true,
            enableResponseHeaderTracking: true,
            enableUnhandledPromiseRejectionTracking: true,
            disableFetchTracking: false,
            disableAjaxTracking: false,
            disablePageUnloadEvents: ["unload", "beforeunload"],
            disableTelemetry: false,
            samplingPercentage: 100,
            maxBatchInterval: 1000,
            extensions: [reactPlugin, clickPlugin],
            extensionConfig: {
                [reactPlugin.identifier]: {},
                [clickPlugin.identifier]: clickPluginConfig,
            },
        },
    });

    appInsights.loadAppInsights();
    appInsights.addTelemetryInitializer((envelope) => {
        envelope.tags = envelope.tags ?? {};
        envelope.tags["ai.cloud.role"] = roleName;
        envelope.tags["ai.cloud.roleInstance"] = roleName;
    });
    appInsights.addTelemetryInitializer(experimentsConfigInitializer);

    appInsightsInstance = appInsights;
    activeConnectionString = connectionString;
    reactPluginInstance = reactPlugin;
    clickPluginInstance = clickPlugin;

    if (!hasTrackedInitialization) {
        hasTrackedInitialization = true;
        trackClientTrace({
            message: "Application Insights initialized",
            properties: {
                source: "browser",
            },
        });
    }

    return appInsights;
};

export const getAppInsights = () => appInsightsInstance;

export const getReactPlugin = () => reactPluginInstance;

export const getClickPlugin = () => clickPluginInstance;

export const trackClientTrace = ({
    measurements,
    message,
    properties,
    severity = "information",
}: TraceTelemetryOptions) => {
    const appInsights = getAppInsights();

    if (!appInsights) {
        if (process.env.NEXT_PUBLIC_NODE_ENV === "development") {
            console.warn(
                "Application Insights trace was not sent because Application Insights has not been initialized.",
                { message, properties, measurements },
            );
        }

        return;
    }

    appInsights.trackTrace(
        {
            message,
            severityLevel: getSeverityLevel(severity),
        },
        {
            ...sanitizeProperties(properties),
            ...sanitizeMeasurements(measurements),
        },
    );
};

export const clientLogger = {
    verbose: (
        message: string,
        properties?: Record<string, unknown>,
        measurements?: Record<string, number>,
    ) =>
        trackClientTrace({
            measurements,
            message,
            properties,
            severity: "verbose",
        }),

    info: (
        message: string,
        properties?: Record<string, unknown>,
        measurements?: Record<string, number>,
    ) =>
        trackClientTrace({
            measurements,
            message,
            properties,
            severity: "information",
        }),

    warn: (
        message: string,
        properties?: Record<string, unknown>,
        measurements?: Record<string, number>,
    ) =>
        trackClientTrace({
            measurements,
            message,
            properties,
            severity: "warning",
        }),

    error: (
        message: string,
        properties?: Record<string, unknown>,
        measurements?: Record<string, number>,
    ) =>
        trackClientTrace({
            measurements,
            message,
            properties,
            severity: "error",
        }),

    critical: (
        message: string,
        properties?: Record<string, unknown>,
        measurements?: Record<string, number>,
    ) =>
        trackClientTrace({
            measurements,
            message,
            properties,
            severity: "critical",
        }),
};
