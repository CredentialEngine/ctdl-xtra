import { createKeycloakBffAuth } from "@credentialengine/auth/server";
import type { NextAuthOptions } from "next-auth";

const SESSION_MAX_AGE_SECONDS = 8 * 60 * 60;

let configPromise: Promise<NextAuthOptions> | undefined;

function readRequiredEnvVar(name: string): string {
    const value = process.env[name];
    if (!value?.trim()) {
        throw new Error(`${name} must be configured for xTRA.`);
    }
    return value;
}

async function buildConfig(): Promise<NextAuthOptions> {
    return createKeycloakBffAuth({
        redisUrl: readRequiredEnvVar("REDIS_URL"),
        redisNamespace: readRequiredEnvVar("BFF_SESSION_NAMESPACE"),
        secret: readRequiredEnvVar("NEXTAUTH_SECRET"),
        sessionMaxAgeSeconds: SESSION_MAX_AGE_SECONDS,
    });
}

export function getAuthConfig(): Promise<NextAuthOptions> {
    if (!configPromise) {
        configPromise = buildConfig();
    }
    return configPromise;
}
