import { createKeycloakBffAuth } from "@credentialengine/auth/server";
import type { NextAuthOptions } from "next-auth";

let cachedConfig: NextAuthOptions | null = null;
let configPromise: Promise<NextAuthOptions> | null = null;

export async function getAuthConfig(): Promise<NextAuthOptions> {
    if (cachedConfig) return cachedConfig;
    if (configPromise) return configPromise;

    configPromise = createKeycloakBffAuth({
        redisUrl: process.env.REDIS_URL,
        redisNamespace:
            process.env.BFF_SESSION_NAMESPACE ?? "credentialengine:xtra",
        sessionMaxAgeSeconds: 8 * 60 * 60,
        secret: () => {
            const secret = process.env.NEXTAUTH_SECRET;
            if (!secret) {
                throw new Error(
                    "NEXTAUTH_SECRET must be provided by the runtime environment.",
                );
            }
            return secret;
        },
    });

    try {
        const config = await configPromise;
        cachedConfig = config;
        return config;
    } finally {
        configPromise = null;
    }
}
