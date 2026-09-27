import { jest } from "@jest/globals";

const getServerSessionMock = jest.fn();
const headersMock = jest.fn(async () => new Headers());
const keycloakProviderMock = jest.fn((options) => ({
    id: "keycloak",
    options,
}));
const nextAuthMock = jest.fn(() => jest.fn(async () => new Response("ok")));

jest.unstable_mockModule("server-only", () => ({}));
jest.unstable_mockModule("next-auth", () => ({
    default: nextAuthMock,
    getServerSession: getServerSessionMock,
}));
jest.unstable_mockModule("next-auth/providers/keycloak", () => ({
    default: keycloakProviderMock,
}));
jest.unstable_mockModule("next/headers", () => ({
    headers: headersMock,
}));

const { NextRequest } = await import("next/server");
const {
    BffUnauthorizedError,
    createBffProxy,
    createKeycloakBffAuth,
    createLogoutRoute,
    getAccessToken,
    getAuthenticatedUser,
    requireAccessToken,
} = await import("../dist/server.js");

function fakeRedis() {
    const values = new Map();
    const calls = { locks: 0, deletes: 0 };
    return {
        values,
        calls,
        async get(key) {
            return values.get(key);
        },
        async set(key, value, options = {}) {
            if (options.NX && values.has(key)) return undefined;
            if (String(key).includes(":nextauth:lock:")) calls.locks += 1;
            values.set(key, value);
            return "OK";
        },
        async del(...keys) {
            let deleted = 0;
            for (const key of keys) {
                if (values.delete(key)) deleted += 1;
            }
            calls.deletes += deleted;
            return deleted;
        },
        async ttl(key) {
            return values.has(key) ? -1 : -2;
        },
        async expire(key) {
            return values.has(key);
        },
        async eval(_script, { keys, arguments: args }) {
            const [key] = keys;
            const [owner] = args;
            if (values.get(key) === owner) {
                values.delete(key);
                return 1;
            }
            return 0;
        },
    };
}

function jwt(payload) {
    return `x.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.y`;
}

async function loginConfig({ encrypted = true, expiresIn = 300 } = {}) {
    const backing = fakeRedis();
    const config = await createKeycloakBffAuth({
        clientId: "finder-client",
        issuer: "https://id.example.test/realms/test",
        secret: "unit-secret",
        redisClient: backing,
        redisNamespace: "credentialengine:test",
        encryptTokens: encrypted,
    });
    const user = await config.adapter.createUser({
        email: "user@example.test",
        emailVerified: null,
        image: null,
        name: "Unit User",
    });
    const account = {
        userId: user.id,
        type: "oauth",
        provider: "keycloak",
        providerAccountId: "keycloak-user-1",
        access_token: jwt({
            realm_access: { roles: ["reader"] },
            resource_access: { "finder-client": { roles: ["editor"] } },
        }),
        refresh_token: jwt({ exp: Math.floor(Date.now() / 1000) + 3600 }),
        id_token: "id-token",
        expires_in: expiresIn,
    };
    await config.adapter.linkAccount(account);
    await config.callbacks.signIn({ user, account });

    const sessionToken = "database-session-token";
    const adapterSession = await config.adapter.createSession({
        sessionToken,
        userId: user.id,
        expires: new Date(Date.now() + 8 * 60 * 60 * 1000),
    });

    getServerSessionMock.mockResolvedValue({
        expires: adapterSession.expires.toISOString(),
        userId: user.id,
        user: { email: user.email, name: user.name },
        roles: ["reader", "editor"],
    });
    headersMock.mockResolvedValue(
        new Headers({ cookie: `next-auth.session-token=${sessionToken}` }),
    );

    return { backing, config, user, account, sessionToken, adapterSession };
}

beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, "error").mockImplementation(() => {});
    jest.spyOn(console, "info").mockImplementation(() => {});
    jest.spyOn(console, "warn").mockImplementation(() => {});
    headersMock.mockResolvedValue(new Headers());
    getServerSessionMock.mockResolvedValue(null);
});

test("createKeycloakBffAuth uses NextAuth database sessions and encrypts OAuth token fields in Account rows", async () => {
    const { backing, config, account, sessionToken } = await loginConfig();

    expect(config.session).toEqual(
        expect.objectContaining({ strategy: "database" }),
    );
    expect(config.adapter).toBeDefined();
    expect(
        backing.values.has(
            `credentialengine:test:nextauth:session:${sessionToken}`,
        ),
    ).toBe(true);

    const accountRow = backing.values.get(
        "credentialengine:test:nextauth:account:keycloak:keycloak-user-1",
    );
    expect(typeof accountRow).toBe("string");
    expect(accountRow).not.toContain(account.access_token);
    expect(accountRow).toContain("enc:v1:");
    expect(keycloakProviderMock).toHaveBeenCalledWith(
        expect.objectContaining({ clientId: "finder-client" }),
    );
});

test("OAuth Account token encryption can be explicitly disabled", async () => {
    const { backing, account } = await loginConfig({
        encrypted: false,
    });
    expect(
        backing.values.get(
            "credentialengine:test:nextauth:account:keycloak:keycloak-user-1",
        ),
    ).toContain(account.access_token);
});

test("database session callback exposes roles and identity metadata but no OAuth tokens", async () => {
    const { config, user, adapterSession } = await loginConfig();
    const session = await config.callbacks.session({
        session: {
            expires: adapterSession.expires.toISOString(),
            user: { email: user.email, name: user.name },
        },
        user,
        newSession: undefined,
        trigger: undefined,
    });
    expect(session.userId).toBe(user.id);
    expect(session.roles).toEqual(expect.arrayContaining(["reader", "editor"]));
    expect(session.accessToken).toBeUndefined();
    expect(session.refreshToken).toBeUndefined();
});

test("getAccessToken and requireAccessToken resolve from the database session token", async () => {
    const { config, account, sessionToken } = await loginConfig();
    const request = new NextRequest("http://localhost/api/test", {
        headers: { cookie: `next-auth.session-token=${sessionToken}` },
    });
    expect(await getAccessToken(config, request)).toBe(account.access_token);
    expect(await requireAccessToken(config, request)).toBe(
        account.access_token,
    );
});

test("missing OAuth Account token state is surfaced as SESSION_EXPIRED", async () => {
    const { config, backing, sessionToken } = await loginConfig();
    const accountKey =
        "credentialengine:test:nextauth:account:keycloak:keycloak-user-1";
    const row = JSON.parse(backing.values.get(accountKey));
    delete row.access_token;
    backing.values.set(accountKey, JSON.stringify(row));
    await expect(
        getAccessToken(
            config,
            new NextRequest("http://localhost/api/test", {
                headers: { cookie: `next-auth.session-token=${sessionToken}` },
            }),
        ),
    ).rejects.toMatchObject({ code: "SESSION_EXPIRED", status: 401 });
});

test("anonymous request returns no optional token and required token throws 401", async () => {
    const { config } = await loginConfig();
    getServerSessionMock.mockResolvedValue(null);
    const request = new NextRequest("http://localhost/api/test");
    expect(await getAccessToken(config, request)).toBeUndefined();
    await expect(requireAccessToken(config, request)).rejects.toBeInstanceOf(
        BffUnauthorizedError,
    );
});

test("getAuthenticatedUser returns database identity and backend roles without returning tokens", async () => {
    const { config, user } = await loginConfig();
    await expect(getAuthenticatedUser(config)).resolves.toEqual({
        id: user.id,
        email: "user@example.test",
        name: "Unit User",
        roles: ["reader", "editor"],
    });
});

test("refresh is performed under the token-store lock and rotates backend tokens", async () => {
    const { backing, config, user, adapterSession } = await loginConfig({
        encrypted: false,
        expiresIn: -1,
    });
    globalThis.fetch = jest.fn(
        async () =>
            new Response(
                JSON.stringify({
                    access_token: jwt({
                        realm_access: { roles: ["refreshed"] },
                    }),
                    refresh_token: jwt({
                        exp: Math.floor(Date.now() / 1000) + 7200,
                    }),
                    expires_in: 600,
                }),
                {
                    status: 200,
                    headers: { "content-type": "application/json" },
                },
            ),
    );

    await config.callbacks.session({
        session: {
            expires: adapterSession.expires.toISOString(),
            user: { email: user.email, name: user.name },
        },
        user,
        newSession: undefined,
        trigger: undefined,
    });

    expect(backing.calls.locks).toBeGreaterThan(0);
    const stored = JSON.parse(
        backing.values.get(
            "credentialengine:test:nextauth:account:keycloak:keycloak-user-1",
        ),
    );
    expect(stored.access_token).toContain(".");
    expect(stored.expires_at).toBeGreaterThan(Math.floor(Date.now() / 1000));
});

test("rejected refresh invalidates the NextAuth database session", async () => {
    const { backing, config, user, adapterSession, sessionToken } =
        await loginConfig({ encrypted: false, expiresIn: -1 });
    globalThis.fetch = jest.fn(
        async () =>
            new Response(JSON.stringify({ error: "invalid_grant" }), {
                status: 400,
                headers: { "content-type": "application/json" },
            }),
    );

    const updated = await config.callbacks.session({
        session: {
            expires: adapterSession.expires.toISOString(),
            user: { email: user.email, name: user.name },
        },
        user,
        newSession: undefined,
        trigger: undefined,
    });
    expect(updated.error).toBe("ReauthenticationRequired");
    expect(
        backing.values.has(
            `credentialengine:test:nextauth:session:${sessionToken}`,
        ),
    ).toBe(false);
});

test("logout is idempotent, deletes the NextAuth database session and clears auth cookies", async () => {
    const { backing, config, sessionToken, user } = await loginConfig({
        encrypted: false,
    });
    process.env.OIDC_AUTHORITY = "";
    process.env.OIDC_CLIENT_ID = "";
    const route = createLogoutRoute(async () => config);
    const request = new NextRequest("http://localhost/api/auth/logout", {
        method: "POST",
        headers: {
            cookie: `next-auth.session-token=${sessionToken}; unrelated=keep`,
        },
    });
    const response = await route(request);

    expect(
        backing.values.has(
            `credentialengine:test:nextauth:session:${sessionToken}`,
        ),
    ).toBe(false);
    expect(
        backing.values.has(
            "credentialengine:test:nextauth:account:keycloak:keycloak-user-1",
        ),
    ).toBe(false);
    expect(
        backing.values.has(`credentialengine:test:nextauth:user:${user.id}`),
    ).toBe(false);
    expect(
        backing.values.has(
            "credentialengine:test:nextauth:user-email:user%40example.test",
        ),
    ).toBe(false);
    expect(
        backing.values.has(
            `credentialengine:test:nextauth:user-accounts:${user.id}`,
        ),
    ).toBe(false);
    expect(response.status).toBe(204);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("set-cookie")).toContain(
        "next-auth.session-token=",
    );
});

test("logout returns 204 without a redirect when no database session exists", async () => {
    const { config } = await loginConfig({ encrypted: false });
    process.env.OIDC_AUTHORITY = "";
    process.env.OIDC_CLIENT_ID = "";
    const route = createLogoutRoute(async () => config);
    const request = new NextRequest("http://localhost/api/auth/logout", {
        method: "POST",
    });

    const response = await route(request);

    expect(response.status).toBe(204);
    expect(response.headers.get("location")).toBeNull();
});

test("BFF proxy sends the per-database-session access token and preserves upstream status", async () => {
    const { config, sessionToken } = await loginConfig();
    globalThis.fetch = jest.fn(async (_url, init) => {
        expect(new Headers(init.headers).get("authorization")).toMatch(
            /^Bearer /,
        );
        return new Response('{"ok":true}', {
            status: 202,
            headers: { "content-type": "application/json", etag: "abc" },
        });
    });
    const proxy = createBffProxy(
        async () => config,
        async () => "https://api.example.test",
    );
    const response = await proxy(
        new NextRequest("http://localhost/api/projects?q=one", {
            headers: { cookie: `next-auth.session-token=${sessionToken}` },
        }),
        ["projects"],
    );
    expect(response.status).toBe(202);
    expect(response.headers.get("etag")).toBe("abc");
});
