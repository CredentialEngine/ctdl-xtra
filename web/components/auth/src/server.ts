import {
    createEncryptedServerSessionStore,
    createJsonServerSessionStore,
    type ServerSessionStore,
} from "@credentialengine/server-session";
import NextAuth, {
    getServerSession,
    type NextAuthOptions,
    type Session,
} from "next-auth";
import { getToken, type JWT } from "next-auth/jwt";
import KeycloakProvider from "next-auth/providers/keycloak";
import { headers } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import "server-only";

export type SecretResolver = string | (() => string | Promise<string>);

export type AuthenticatedUser = {
    id: string;
    email: string;
    name: string | null;
    roles: string[];
};

export type ServerTokenSession = {
    accessToken: string;
    refreshToken?: string;
    idToken?: string;
    /** Epoch seconds — when the access token expires. */
    expiresAtEpochSec: number;
    /** Epoch milliseconds — when the overall BFF session expires. */
    sessionExpiresAtMs: number;
    roles: string[];
};

export type KeycloakBffOptions = {
    clientId?: string;
    issuer?: string;
    secret: SecretResolver;
    refreshBufferMs?: number;
    providerId?: string;
    sessionMaxAgeSeconds?: number;
    tokenStore: ServerSessionStore<string>;
    /** Overrides BFF_SESSION_ENCRYPTION when provided. Encryption defaults to enabled. */
    encryptTokenStore?: boolean;
};

export type ClientTokenConfig = {
    issuer: string;
    clientId: string;
    clientSecret: string;
};

export type BffUnauthorizedCode = "UNAUTHORIZED" | "SESSION_EXPIRED";

export class BffUnauthorizedError extends Error {
    readonly status = 401;

    constructor(
        message = "Not authenticated",
        readonly code: BffUnauthorizedCode = "UNAUTHORIZED",
    ) {
        super(message);
        this.name = "BffUnauthorizedError";
    }
}

class ReauthenticationRequiredError extends Error {
    constructor(message = "Authentication expired. Sign in again.") {
        super(message);
        this.name = "ReauthenticationRequiredError";
    }
}

const DEFAULT_SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;
const configStores = new WeakMap<
    NextAuthOptions,
    ServerSessionStore<ServerTokenSession>
>();

type JwtWithServerId = JWT & { bffSessionId?: string };

function getTokenStore(
    config: NextAuthOptions,
): ServerSessionStore<ServerTokenSession> {
    const store = configStores.get(config);
    if (!store) {
        throw new Error(
            "No server token store is registered for this auth configuration.",
        );
    }
    return store;
}

function rolesFromToken(accessToken: string, clientId: string): string[] {
    try {
        const payload = JSON.parse(
            Buffer.from(accessToken.split(".")[1], "base64url").toString(
                "utf8",
            ),
        );
        const realmRoles = Array.isArray(payload.realm_access?.roles)
            ? payload.realm_access.roles
            : [];
        const clientRoles = Array.isArray(
            payload.resource_access?.[clientId]?.roles,
        )
            ? payload.resource_access[clientId].roles
            : [];
        return [...new Set<string>([...realmRoles, ...clientRoles])];
    } catch {
        return [];
    }
}

async function resolveSecret(secret: SecretResolver): Promise<string> {
    const value = typeof secret === "function" ? await secret() : secret;
    if (!value) {
        throw new Error("NextAuth secret is required.");
    }
    return value;
}

function remainingSessionTtlSeconds(session: ServerTokenSession): number {
    return Math.max(
        1,
        Math.ceil((session.sessionExpiresAtMs - Date.now()) / 1000),
    );
}

function isExpiredJwt(token: string): boolean {
    const parts = token.split(".");
    if (parts.length !== 3) {
        return false;
    }
    try {
        const payload = JSON.parse(
            Buffer.from(parts[1], "base64url").toString("utf8"),
        ) as {
            exp?: number;
        };
        return (
            typeof payload.exp === "number" && payload.exp * 1000 <= Date.now()
        );
    } catch {
        return false;
    }
}

function refreshWasRejected(status: number, error?: string): boolean {
    return (
        status === 400 ||
        status === 401 ||
        error === "invalid_grant" ||
        error === "invalid_token"
    );
}

async function refreshServerSession(
    sessionId: string,
    store: ServerSessionStore<ServerTokenSession>,
    clientId: string,
    issuer: string,
    refreshBufferMs: number,
): Promise<ServerTokenSession> {
    return store.withLock(sessionId, async () => {
        // Re-read after acquiring the distributed lock. Another pod may already have
        // refreshed and rotated the refresh token while this request was waiting.
        const current = await store.get(sessionId);
        if (!current) {
            throw new Error("Missing server session.");
        }

        if (current.sessionExpiresAtMs <= Date.now()) {
            await store.delete(sessionId);
            throw new Error("Server session expired.");
        }

        if (Date.now() < current.expiresAtEpochSec * 1000 - refreshBufferMs) {
            return current;
        }

        if (!current.refreshToken || isExpiredJwt(current.refreshToken)) {
            await store.delete(sessionId);
            throw new ReauthenticationRequiredError(
                "Refresh token is missing or expired.",
            );
        }

        const response = await fetch(
            `${issuer}/protocol/openid-connect/token`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: new URLSearchParams({
                    client_id: clientId,
                    grant_type: "refresh_token",
                    refresh_token: current.refreshToken,
                }),
                cache: "no-store",
            },
        );

        const body = (await response.json()) as {
            access_token?: string;
            refresh_token?: string;
            id_token?: string;
            expires_in?: number;
            error?: string;
            error_description?: string;
        };

        if (!response.ok || !body.access_token || !body.expires_in) {
            const message =
                body.error_description ??
                body.error ??
                `Token refresh failed (${response.status})`;
            if (refreshWasRejected(response.status, body.error)) {
                await store.delete(sessionId);
                throw new ReauthenticationRequiredError(message);
            }
            throw new Error(message);
        }

        const updated: ServerTokenSession = {
            accessToken: body.access_token,
            refreshToken: body.refresh_token ?? current.refreshToken,
            idToken: body.id_token ?? current.idToken,
            expiresAtEpochSec: Math.floor(Date.now() / 1000) + body.expires_in,
            sessionExpiresAtMs: current.sessionExpiresAtMs,
            roles: rolesFromToken(body.access_token, clientId),
        };

        await store.set(
            sessionId,
            updated,
            remainingSessionTtlSeconds(updated),
        );
        return updated;
    });
}

export async function createKeycloakBffAuth(
    options: KeycloakBffOptions,
): Promise<NextAuthOptions> {
    const clientId = options.clientId ?? process.env.OIDC_CLIENT_ID;
    const issuer = options.issuer ?? process.env.OIDC_AUTHORITY;
    if (!clientId || !issuer) {
        throw new Error(
            "OIDC_CLIENT_ID and OIDC_AUTHORITY must be configured.",
        );
    }

    const secret = await resolveSecret(options.secret);
    const encryptionEnv =
        process.env.BFF_SESSION_ENCRYPTION?.trim().toLowerCase();
    const encryptTokenStore =
        options.encryptTokenStore ??
        !["false", "0", "off", "no"].includes(encryptionEnv ?? "");

    // OAuth tokens always remain backend-only. Encryption controls only how the
    // server-side backing store persists the token-session payload.
    const store = encryptTokenStore
        ? createEncryptedServerSessionStore<ServerTokenSession>(
              options.tokenStore,
              {
                  secret,
                  purpose: `oauth-tokens:${clientId}`,
              },
          )
        : createJsonServerSessionStore<ServerTokenSession>(options.tokenStore);

    console.info("[auth] Server token-store persistence", {
        encrypted: encryptTokenStore,
    });
    const refreshBufferMs = options.refreshBufferMs ?? 30_000;
    const sessionMaxAgeSeconds =
        options.sessionMaxAgeSeconds ?? DEFAULT_SESSION_MAX_AGE_SECONDS;

    const config: NextAuthOptions = {
        secret,
        session: { strategy: "jwt", maxAge: sessionMaxAgeSeconds },
        providers: [
            KeycloakProvider({
                clientId,
                clientSecret: "",
                issuer,
                client: { token_endpoint_auth_method: "none" },
                checks: ["pkce", "state"],
            }),
        ],
        callbacks: {
            async jwt({ token, account, trigger, session: updateData }) {
                const jwt = token as JwtWithServerId;

                // Defensive migration cleanup: never persist OAuth token material in the
                // NextAuth JWT cookie. Only the opaque bffSessionId is browser-held.
                delete jwt.accessToken;
                delete jwt.refreshToken;
                delete jwt.idToken;
                delete jwt.expiresAt;

                if (
                    trigger === "update" &&
                    updateData &&
                    "activeTenantId" in updateData
                ) {
                    jwt.activeTenantId = updateData.activeTenantId || undefined;
                    return jwt;
                }

                if (account?.access_token) {
                    const sessionId = jwt.bffSessionId ?? randomUUID();
                    const expiresIn =
                        typeof account.expires_in === "number"
                            ? account.expires_in
                            : Number(account.expires_in);
                    const expiresAtEpochSec =
                        typeof account.expires_at === "number"
                            ? account.expires_at
                            : Math.floor(Date.now() / 1000) +
                              (Number.isFinite(expiresIn) ? expiresIn : 300);
                    const sessionExpiresAtMs =
                        Date.now() + sessionMaxAgeSeconds * 1000;

                    const serverSession: ServerTokenSession = {
                        accessToken: account.access_token,
                        refreshToken: account.refresh_token,
                        idToken: account.id_token,
                        expiresAtEpochSec,
                        sessionExpiresAtMs,
                        roles: rolesFromToken(account.access_token, clientId),
                    };

                    await store.set(
                        sessionId,
                        serverSession,
                        sessionMaxAgeSeconds,
                    );
                    jwt.bffSessionId = sessionId;
                    jwt.error = undefined;
                    return jwt;
                }

                if (!jwt.bffSessionId) {
                    jwt.error = "MissingServerSession";
                    return jwt;
                }

                const serverSession = await store.get(jwt.bffSessionId);
                if (!serverSession) {
                    jwt.error = "MissingServerSession";
                    return jwt;
                }

                if (serverSession.sessionExpiresAtMs <= Date.now()) {
                    await store.delete(jwt.bffSessionId);
                    jwt.error = "ExpiredServerSession";
                    return jwt;
                }

                if (
                    Date.now() <
                    serverSession.expiresAtEpochSec * 1000 - refreshBufferMs
                ) {
                    jwt.error = undefined;
                    return jwt;
                }

                try {
                    await refreshServerSession(
                        jwt.bffSessionId,
                        store,
                        clientId,
                        issuer,
                        refreshBufferMs,
                    );
                    jwt.error = undefined;
                } catch (error) {
                    console.error("[auth] access token refresh failed", error);
                    if (error instanceof ReauthenticationRequiredError) {
                        jwt.error = "ReauthenticationRequired";
                    } else {
                        jwt.error = "RefreshAccessTokenError";
                    }
                }
                return jwt;
            },

            async session({ session, token }) {
                const jwt = token as JwtWithServerId;
                const serverSession = jwt.bffSessionId
                    ? await store.get(jwt.bffSessionId)
                    : undefined;

                session.error = jwt.error as string | undefined;
                session.userId = jwt.sub;
                session.roles = serverSession?.roles ?? [];
                session.activeTenantId = jwt.activeTenantId as
                    string | undefined;
                return session;
            },
        },
    };

    configStores.set(config, store);
    return config;
}

export function createNextAuthRoute(getConfig: () => Promise<NextAuthOptions>) {
    return async (
        req: Request,
        ctx: { params: Promise<{ nextauth: string[] }> },
    ) => {
        const params = await ctx.params;
        return NextAuth(await getConfig())(req, { params });
    };
}

async function getRequestJwt(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<JwtWithServerId | null> {
    if (request) {
        return (await getToken({
            req: request,
            secret: String(config.secret),
        })) as JwtWithServerId | null;
    }

    const requestHeaders = await headers();
    const syntheticRequest = new NextRequest("http://localhost", {
        headers: new Headers(requestHeaders),
    });
    return (await getToken({
        req: syntheticRequest,
        secret: String(config.secret),
    })) as JwtWithServerId | null;
}

async function getServerTokenSession(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<ServerTokenSession | undefined> {
    const session = await getServerSession(config);
    const jwt = await getRequestJwt(config, request);

    if (!jwt?.bffSessionId) {
        return undefined;
    }
    if (!session || session.error) {
        throw new BffUnauthorizedError(
            "Authentication expired. Sign in again.",
            "SESSION_EXPIRED",
        );
    }

    const serverSession = await getTokenStore(config).get(jwt.bffSessionId);
    if (!serverSession) {
        throw new BffUnauthorizedError(
            "Authentication expired. Sign in again.",
            "SESSION_EXPIRED",
        );
    }
    return serverSession;
}

export async function getAccessToken(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<string | undefined> {
    const session = await getServerTokenSession(config, request);
    if (!session) {
        return undefined;
    }
    return session.accessToken;
}

export async function requireAccessToken(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<string> {
    const accessToken = await getAccessToken(config, request);
    if (!accessToken) {
        throw new BffUnauthorizedError();
    }
    return accessToken;
}

/**
 * Compatibility helper for code that also needs normal session metadata.
 * OAuth tokens in this returned object exist only in server memory for this call;
 * refresh tokens are never returned by this API.
 */
export async function getBffSession(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<Session & { accessToken?: string; idToken?: string }> {
    const session = await getServerSession(config);
    const baseSession = session ?? ({ expires: "" } as Session);
    if (!session || session.error) {
        return { ...baseSession };
    }

    const jwt = await getRequestJwt(config, request);
    const serverSession = jwt?.bffSessionId
        ? await getTokenStore(config).get(jwt.bffSessionId)
        : undefined;

    return {
        ...baseSession,
        accessToken: serverSession?.accessToken,
        idToken: serverSession?.idToken,
    };
}

export async function getAuthenticatedSession(
    config: NextAuthOptions,
): Promise<Session | undefined> {
    const session = await getServerSession(config);
    if (!session || session.error || !session.userId) {
        return undefined;
    }
    return session;
}

export async function getAuthenticatedUser(
    config: NextAuthOptions,
): Promise<AuthenticatedUser | undefined> {
    const session = await getServerSession(config);
    const serverTokenSession = await getServerTokenSession(config);

    if (!serverTokenSession) {
        return undefined;
    }

    if (!session || !session.user?.email || !session.userId) {
        return undefined;
    }

    return {
        id: session.userId,
        email: session.user.email,
        name: session.user.name ?? null,
        roles: serverTokenSession.roles,
    };
}

function clearAuthCookies(request: NextRequest, response: NextResponse) {
    const authPrefixes = [
        "next-auth.",
        "__Secure-next-auth.",
        "__Host-next-auth.",
        "authjs.",
        "__Secure-authjs.",
        "__Host-authjs.",
    ];

    for (const cookie of request.cookies.getAll()) {
        const isAuthCookie = authPrefixes.some((prefix) =>
            cookie.name.startsWith(prefix),
        );
        if (isAuthCookie) {
            response.cookies.set(cookie.name, "", {
                expires: new Date(0),
                httpOnly: true,
                sameSite: "lax",
                secure: request.nextUrl.protocol === "https:",
                path: "/",
            });
        }
    }
}

export function createLogoutRoute(getConfig: () => Promise<NextAuthOptions>) {
    return async (request: NextRequest) => {
        const config = await getConfig();
        const jwt = await getRequestJwt(config, request);
        const sessionId = jwt?.bffSessionId;
        const store = getTokenStore(config);
        let serverSession: ServerTokenSession | undefined;

        if (sessionId) {
            // Serialize logout with token refresh. A refresh that began just before
            // logout cannot write a new token record back after this deletion.
            await store.withLock(sessionId, async () => {
                serverSession = await store.get(sessionId);
                await store.delete(sessionId);
            });
            console.info("[bff-auth] Server session deleted", {
                sessionIdPresent: true,
            });
        }

        const issuer = process.env.OIDC_AUTHORITY;
        const clientId = process.env.OIDC_CLIENT_ID;

        // The BFF session has already been destroyed above. Retain the idToken only
        // in this request-local variable for a best-effort IdP logout.
        if (serverSession?.idToken && issuer && clientId) {
            await fetch(`${issuer}/protocol/openid-connect/logout`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: new URLSearchParams({
                    id_token_hint: serverSession.idToken,
                    client_id: clientId,
                }),
                cache: "no-store",
            }).catch((error) => {
                console.warn(
                    "[bff-auth] Identity-provider logout failed after local session deletion",
                    {
                        message:
                            error instanceof Error
                                ? error.message
                                : "Unknown error",
                    },
                );
            });
        }

        const response = new NextResponse(null, { status: 204 });
        clearAuthCookies(request, response);
        return response;
    };
}

export function createBffProxy(
    getConfig: () => Promise<NextAuthOptions>,
    getBaseUrl: (request: NextRequest) => string | Promise<string>,
) {
    return async (request: NextRequest, path: string[]) => {
        let accessToken: string;
        try {
            accessToken = await requireAccessToken(await getConfig(), request);
        } catch (error) {
            if (error instanceof BffUnauthorizedError) {
                return NextResponse.json(
                    { error: error.message, code: error.code },
                    { status: 401 },
                );
            }
            throw error;
        }

        if (!["GET", "HEAD", "OPTIONS"].includes(request.method)) {
            const origin = request.headers.get("origin");
            if (origin && origin !== request.nextUrl.origin) {
                return NextResponse.json(
                    { error: "Cross-site request rejected" },
                    { status: 403 },
                );
            }
        }

        let url: URL;
        try {
            const base = (await getBaseUrl(request)).trim().replace(/\/$/, "");
            if (!base) {
                throw new Error("BFF upstream base URL is empty.");
            }
            url = new URL(`${base}/${path.map(encodeURIComponent).join("/")}`);
            request.nextUrl.searchParams.forEach((value, key) =>
                url.searchParams.append(key, value),
            );
        } catch (error) {
            console.error(
                "[bff] invalid or missing upstream configuration",
                error,
            );
            return NextResponse.json(
                { error: "BFF upstream is not configured" },
                { status: 502 },
            );
        }

        const headersOut = new Headers();
        for (const name of [
            "accept",
            "content-type",
            "if-match",
            "if-none-match",
        ]) {
            const value = request.headers.get(name);
            if (value) {
                headersOut.set(name, value);
            }
        }
        headersOut.set("authorization", `Bearer ${accessToken}`);

        const body = ["GET", "HEAD"].includes(request.method)
            ? undefined
            : await request.arrayBuffer();

        let upstream: Response;
        try {
            upstream = await fetch(url, {
                method: request.method,
                headers: headersOut,
                body,
                cache: "no-store",
                redirect: "manual",
            });
        } catch (error) {
            console.error("[bff] upstream request failed", {
                method: request.method,
                url: url.toString(),
                error,
            });
            return NextResponse.json(
                { error: "Upstream service unavailable" },
                { status: 502 },
            );
        }

        const responseHeaders = new Headers();
        for (const name of [
            "content-type",
            "content-disposition",
            "etag",
            "last-modified",
        ]) {
            const value = upstream.headers.get(name);
            if (value) {
                responseHeaders.set(name, value);
            }
        }

        return new NextResponse(upstream.body, {
            status: upstream.status,
            headers: responseHeaders,
        });
    };
}

// TODO: Supports only one service client. If multiple
// apps need different credentials, replace cache with a Map keyed by clientId.
let clientTokenCache: string | undefined;
let clientTokenExpiresAt = 0;

const SERVICE_TOKEN_REFRESH_BUFFER_MS = 30_000;

export async function getClientToken(
    config: ClientTokenConfig,
): Promise<string> {
    if (
        clientTokenCache &&
        Date.now() < clientTokenExpiresAt - SERVICE_TOKEN_REFRESH_BUFFER_MS
    ) {
        return clientTokenCache;
    }

    const response = await fetch(
        `${config.issuer}/protocol/openid-connect/token`,
        {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body: new URLSearchParams({
                client_id: config.clientId,
                client_secret: config.clientSecret,
                grant_type: "client_credentials",
            }),
            cache: "no-store",
        },
    );

    if (!response.ok) {
        throw new Error(`Client credentials grant failed (${response.status})`);
    }

    const body = (await response.json()) as {
        access_token: string;
        expires_in: number;
    };

    clientTokenCache = body.access_token;
    clientTokenExpiresAt = Date.now() + body.expires_in * 1000;

    return clientTokenCache;
}

export type TokenResolver = (
    request: NextRequest,
) => Promise<string | undefined>;

export function createTokenResolverChain(
    ...resolvers: TokenResolver[]
): TokenResolver {
    return async (request: NextRequest) => {
        for (const resolver of resolvers) {
            const token = await resolver(request);
            if (token) {
                return token;
            }
        }
        return undefined;
    };
}

export function userTokenResolver(
    getConfig: () => Promise<NextAuthOptions>,
): TokenResolver {
    return async (request) => {
        try {
            return await getAccessToken(await getConfig(), request);
        } catch (error) {
            if (
                error instanceof BffUnauthorizedError &&
                error.code === "SESSION_EXPIRED"
            ) {
                return undefined;
            }
            throw error;
        }
    };
}

export function clientTokenResolver(config: ClientTokenConfig): TokenResolver {
    return async () => {
        return await getClientToken(config);
    };
}

declare module "next-auth" {
    interface Session {
        error?: string;
        userId?: string;
        roles?: string[];
        activeTenantId?: string;
    }
}

declare module "next-auth/jwt" {
    interface JWT {
        bffSessionId?: string;
        error?: string;
        activeTenantId?: string;
        // Legacy fields are declared only so old cookies can be safely stripped.
        accessToken?: string;
        refreshToken?: string;
        expiresAt?: number;
        idToken?: string;
    }
}
