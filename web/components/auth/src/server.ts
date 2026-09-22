import {
    createRedisClient,
    type RedisClient,
} from "@credentialengine/redis-client";
import NextAuth, {
    getServerSession,
    type NextAuthOptions,
    type Session,
} from "next-auth";
import type { AdapterAccount } from "next-auth/adapters";
import KeycloakProvider from "next-auth/providers/keycloak";
import { headers } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import "server-only";
import {
    createRedisNextAuthStore,
    type RedisNextAuthStore,
} from "./store-adapter.js";

export type SecretResolver = string | (() => string | Promise<string>);

export type AuthenticatedUser = {
    id: string;
    email: string;
    name: string | null;
    roles: string[];
};

export type KeycloakBffOptions = {
    clientId?: string;
    issuer?: string;
    secret: SecretResolver;
    refreshBufferMs?: number;
    providerId?: string;
    sessionMaxAgeSeconds?: number;
    redisUrl?: string;
    redisNamespace?: string;
    /** Primarily for tests or applications that already own the Redis client. */
    redisClient?: RedisClient;
    /** Overrides BFF_TOKEN_ENCRYPTION when provided. Token encryption defaults to enabled. */
    encryptTokens?: boolean;
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

type AuthState = {
    store: RedisNextAuthStore;
    providerId: string;
    clientId: string;
    issuer: string;
    refreshBufferMs: number;
};

const configStores = new WeakMap<NextAuthOptions, AuthState>();

function getAuthState(config: NextAuthOptions): AuthState {
    const state = configStores.get(config);
    if (!state) {
        throw new Error(
            "No Redis-backed auth state is registered for this auth configuration.",
        );
    }
    return state;
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

function isExpiredJwt(token: string): boolean {
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    try {
        const payload = JSON.parse(
            Buffer.from(parts[1], "base64url").toString("utf8"),
        ) as { exp?: number };
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

function accountExpiresAtEpochSec(account: {
    expires_at?: number | null;
    expires_in?: number | string | null;
}): number {
    if (typeof account.expires_at === "number") return account.expires_at;
    const expiresIn = Number(account.expires_in);
    return (
        Math.floor(Date.now() / 1000) +
        (Number.isFinite(expiresIn) ? expiresIn : 300)
    );
}

async function accountForUser(
    state: AuthState,
    userId: string,
): Promise<AdapterAccount | undefined> {
    const accounts = await state.store.getAccountsForUser(userId);
    return (
        accounts.find((account) => account.provider === state.providerId) ??
        accounts[0]
    );
}

async function refreshAccountTokens(
    state: AuthState,
    account: AdapterAccount,
): Promise<AdapterAccount> {
    const lockName = `refresh:${account.provider}:${account.providerAccountId}`;
    return state.store.withLock(lockName, async () => {
        const current = await state.store.getAccount(
            account.provider,
            account.providerAccountId,
        );
        if (!current?.access_token) {
            throw new ReauthenticationRequiredError(
                "OAuth account token state is missing.",
            );
        }

        const currentExpiresAt = accountExpiresAtEpochSec(current);
        if (Date.now() < currentExpiresAt * 1000 - state.refreshBufferMs) {
            return current;
        }

        if (!current.refresh_token || isExpiredJwt(current.refresh_token)) {
            throw new ReauthenticationRequiredError(
                "Refresh token is missing or expired.",
            );
        }

        const response = await fetch(
            `${state.issuer}/protocol/openid-connect/token`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: new URLSearchParams({
                    client_id: state.clientId,
                    grant_type: "refresh_token",
                    refresh_token: current.refresh_token,
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
                throw new ReauthenticationRequiredError(message);
            }
            throw new Error(message);
        }

        const updated: AdapterAccount = {
            ...current,
            access_token: body.access_token,
            refresh_token: body.refresh_token ?? current.refresh_token,
            id_token: body.id_token ?? current.id_token,
            expires_at: Math.floor(Date.now() / 1000) + body.expires_in,
        };
        await state.store.upsertAccount(updated);
        return updated;
    });
}

async function currentAccount(
    state: AuthState,
    userId: string,
): Promise<AdapterAccount | undefined> {
    let account = await accountForUser(state, userId);
    if (!account?.access_token) return account;

    if (
        Date.now() >=
        accountExpiresAtEpochSec(account) * 1000 - state.refreshBufferMs
    ) {
        account = await refreshAccountTokens(state, account);
    }
    return account;
}

function tokenEncryptionEnabled(explicit?: boolean): boolean {
    if (explicit !== undefined) return explicit;
    const value = process.env.BFF_TOKEN_ENCRYPTION?.trim().toLowerCase();
    return !["false", "0", "off", "no"].includes(value ?? "");
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
    const redisUrl = options.redisUrl ?? process.env.REDIS_URL;
    const redis =
        options.redisClient ??
        (redisUrl ? createRedisClient({ url: redisUrl }) : undefined);
    if (!redis) {
        throw new Error(
            "REDIS_URL must be configured for NextAuth database sessions.",
        );
    }

    const encryptTokens = tokenEncryptionEnabled(options.encryptTokens);
    const sessionMaxAgeSeconds =
        options.sessionMaxAgeSeconds ?? DEFAULT_SESSION_MAX_AGE_SECONDS;
    const refreshBufferMs = options.refreshBufferMs ?? 30_000;
    const redisNamespace =
        options.redisNamespace ??
        process.env.BFF_SESSION_NAMESPACE ??
        "credentialengine:xtra";

    const store = createRedisNextAuthStore({
        redis,
        namespace: redisNamespace,
        encryptTokens,
        encryptionSecret: secret,
    });

    console.info("[auth] Redis NextAuth persistence", {
        tokenEncryption: encryptTokens,
        sessionStrategy: "database",
        namespace: redisNamespace,
    });

    const keycloakProvider = {
        ...KeycloakProvider({
            clientId,
            clientSecret: "",
            issuer,
            client: { token_endpoint_auth_method: "none" },
            checks: ["pkce", "state"],
        }),
        ...(options.providerId ? { id: options.providerId } : {}),
    };

    const state: AuthState = {
        store,
        providerId: keycloakProvider.id,
        clientId,
        issuer,
        refreshBufferMs,
    };

    const config: NextAuthOptions = {
        secret,
        adapter: store.adapter,
        session: {
            strategy: "database",
            maxAge: sessionMaxAgeSeconds,
            updateAge: 60 * 60,
        },
        providers: [keycloakProvider],
        callbacks: {
            async signIn({ account }) {
                if (!account) return true;

                // On the first login NextAuth's adapter linkAccount() persists the
                // account with the canonical database userId. On a repeat login,
                // refresh token fields on that already-linked account without
                // creating a second user/account index from the provider profile id.
                const existing = await store.getAccount(
                    account.provider,
                    account.providerAccountId,
                );
                if (existing) {
                    const persisted: AdapterAccount = {
                        ...existing,
                        ...account,
                        userId: existing.userId,
                        expires_at: accountExpiresAtEpochSec(account),
                    };
                    await store.upsertAccount(persisted);
                }
                return true;
            },

            async session(params) {
                const session = params.session;
                if (!("user" in params) || !params.user) return session;
                const user = params.user;
                const trigger =
                    "trigger" in params ? params.trigger : undefined;
                const newSession =
                    "newSession" in params ? params.newSession : undefined;

                session.userId = user.id;
                const sessionToken = await getDatabaseSessionToken(config);
                if (!sessionToken) {
                    session.error = "MissingDatabaseSession";
                    session.roles = [];
                    return session;
                }

                if (
                    trigger === "update" &&
                    newSession &&
                    typeof newSession === "object" &&
                    "activeTenantId" in newSession
                ) {
                    const metadata =
                        await store.getSessionMetadata(sessionToken);
                    const requestedTenant = (
                        newSession as {
                            activeTenantId?: unknown;
                        }
                    ).activeTenantId;
                    metadata.activeTenantId =
                        typeof requestedTenant === "string" && requestedTenant
                            ? requestedTenant
                            : undefined;
                    await store.setSessionMetadata(
                        sessionToken,
                        metadata,
                        new Date(session.expires),
                    );
                }

                const metadata = await store.getSessionMetadata(sessionToken);
                session.activeTenantId = metadata.activeTenantId;

                try {
                    const account = await currentAccount(state, user.id);
                    if (!account?.access_token) {
                        session.error = "MissingOAuthAccount";
                        session.roles = [];
                        return session;
                    }
                    session.error = undefined;
                    session.roles = rolesFromToken(
                        account.access_token,
                        clientId,
                    );
                } catch (error) {
                    console.error("[auth] access token refresh failed", error);
                    if (error instanceof ReauthenticationRequiredError) {
                        await config.adapter?.deleteSession?.(sessionToken);
                        session.error = "ReauthenticationRequired";
                    } else {
                        session.error = "RefreshAccessTokenError";
                    }
                    session.roles = [];
                }
                return session;
            },
        },
    };

    configStores.set(config, state);
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

async function getDatabaseSessionToken(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<string | undefined> {
    const names = [
        config.cookies?.sessionToken?.name,
        "__Secure-next-auth.session-token",
        "next-auth.session-token",
    ].filter((name): name is string => Boolean(name));

    const source =
        request ??
        new NextRequest("http://localhost", {
            headers: new Headers(await headers()),
        });

    for (const name of names) {
        const value = source.cookies.get(name)?.value;
        if (value) return value;
    }
    return undefined;
}

async function accountForAuthenticatedSession(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<AdapterAccount | undefined> {
    const session = await getServerSession(config);
    if (!session) return undefined;
    if (session.error || !session.userId) {
        throw new BffUnauthorizedError(
            "Authentication expired. Sign in again.",
            "SESSION_EXPIRED",
        );
    }

    const sessionToken = await getDatabaseSessionToken(config, request);
    if (!sessionToken) {
        throw new BffUnauthorizedError(
            "Authentication session cookie is missing.",
            "SESSION_EXPIRED",
        );
    }

    const state = getAuthState(config);
    try {
        const account = await currentAccount(state, session.userId);
        if (!account?.access_token) {
            throw new BffUnauthorizedError(
                "Authentication provider token state is missing.",
                "SESSION_EXPIRED",
            );
        }
        return account;
    } catch (error) {
        if (error instanceof ReauthenticationRequiredError) {
            await config.adapter?.deleteSession?.(sessionToken);
            throw new BffUnauthorizedError(
                "Authentication expired. Sign in again.",
                "SESSION_EXPIRED",
            );
        }
        throw error;
    }
}

export async function getAccessToken(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<string | undefined> {
    const account = await accountForAuthenticatedSession(config, request);
    return account?.access_token;
}

export async function requireAccessToken(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<string> {
    const accessToken = await getAccessToken(config, request);
    if (!accessToken) throw new BffUnauthorizedError();
    return accessToken;
}

/**
 * Compatibility helper for server code that needs normal session metadata plus
 * the current provider access/id token. Refresh tokens are never returned.
 */
export async function getBffSession(
    config: NextAuthOptions,
    request?: NextRequest,
): Promise<Session & { accessToken?: string; idToken?: string }> {
    // Kept for API compatibility with callers that pass the current request.
    // getServerSession reads the active request context directly.
    void request;
    const session = await getServerSession(config);
    const baseSession = session ?? ({ expires: "" } as Session);
    if (!session || session.error || !session.userId) return { ...baseSession };

    try {
        const account = await currentAccount(
            getAuthState(config),
            session.userId,
        );
        return {
            ...baseSession,
            accessToken: account?.access_token,
            idToken: account?.id_token,
        };
    } catch {
        return { ...baseSession };
    }
}

export async function getAuthenticatedSession(
    config: NextAuthOptions,
): Promise<Session | undefined> {
    const session = await getServerSession(config);
    if (!session || session.error || !session.userId) return undefined;
    return session;
}

export async function getAuthenticatedUser(
    config: NextAuthOptions,
): Promise<AuthenticatedUser | undefined> {
    const session = await getServerSession(config);
    if (!session || session.error || !session.user?.email || !session.userId) {
        return undefined;
    }

    const account = await currentAccount(getAuthState(config), session.userId);
    if (!account?.access_token) return undefined;

    return {
        id: session.userId,
        email: session.user.email,
        name: session.user.name ?? null,
        roles: rolesFromToken(
            account.access_token,
            getAuthState(config).clientId,
        ),
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
        if (authPrefixes.some((prefix) => cookie.name.startsWith(prefix))) {
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
        const state = getAuthState(config);
        const sessionToken = await getDatabaseSessionToken(config, request);
        let account: AdapterAccount | undefined;

        if (sessionToken) {
            const sessionAndUser =
                await config.adapter?.getSessionAndUser?.(sessionToken);
            if (sessionAndUser?.user.id) {
                account = await accountForUser(state, sessionAndUser.user.id);
            }
            await config.adapter?.deleteSession?.(sessionToken);
            console.info("[bff-auth] Database session deleted", {
                sessionTokenPresent: true,
            });
        }

        // Delete the local database session first. Provider logout is best-effort.
        if (account?.id_token) {
            await fetch(`${state.issuer}/protocol/openid-connect/logout`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                body: new URLSearchParams({
                    id_token_hint: account.id_token,
                    client_id: state.clientId,
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
