import { createKeycloakBffAuth } from "@credentialengine/auth/server";
import { createEnvironmentServerSessionStore } from "@credentialengine/server-session";
import type { NextAuthOptions } from "next-auth";

let cachedConfig: NextAuthOptions | null = null;
let configPromise: Promise<NextAuthOptions> | null = null;

const tokenStore = createEnvironmentServerSessionStore<string>({
    namespace: process.env.BFF_SESSION_NAMESPACE ?? "credentialengine:xtra",
});

export async function getAuthConfig(): Promise<NextAuthOptions> {
    if (cachedConfig) return cachedConfig;
    if (configPromise) return configPromise;

    configPromise = createKeycloakBffAuth({
        tokenStore,
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
