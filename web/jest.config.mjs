import { fileURLToPath } from "node:url";

const webRoot = fileURLToPath(new URL(".", import.meta.url));

/** @type {import("jest").Config} */
const common = {
    rootDir: webRoot,
    testEnvironment: "node",
    transform: {},
    clearMocks: true,
    restoreMocks: true,
    modulePathIgnorePatterns: ["<rootDir>/xtra/.next/"],
    moduleNameMapper: {
        "^server-only$": "<rootDir>/components/jest/server-only.mjs",
    },
};

const config = {
    projects: [
        {
            ...common,
            displayName: "server-session",
            testMatch: [
                "<rootDir>/components/server-session/src/**/*.test.mjs",
            ],
        },
        {
            ...common,
            displayName: "auth",
            testMatch: ["<rootDir>/components/auth/src/**/*.test.mjs"],
        },
        {
            ...common,
            displayName: "app-insights",
            testMatch: ["<rootDir>/components/appInsights/src/**/*.test.mjs"],
        },
        {
            ...common,
            displayName: "telemetry",
            testMatch: ["<rootDir>/components/telemetry/src/**/*.test.mjs"],
        },
        {
            ...common,
            displayName: "redis-client",
            testMatch: ["<rootDir>/components/redis-client/src/**/*.test.mjs"],
        },
    ],
};

export default config;
