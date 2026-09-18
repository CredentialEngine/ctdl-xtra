import { jest } from "@jest/globals";

const getServerSessionMock = jest.fn();
const getTokenMock = jest.fn();
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
jest.unstable_mockModule("next-auth/jwt", () => ({ getToken: getTokenMock }));
jest.unstable_mockModule("next-auth/providers/keycloak", () => ({
    default: keycloakProviderMock,
}));
jest.unstable_mockModule("next/headers", () => ({
    headers: jest.fn(async () => new Headers()),
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

function rawStore() {
    const values = new Map();
    const calls = { locks: 0, deletes: 0 };
    return {
        values,
        calls,
        async get(id) {
            return values.get(id);
        },
        async set(id, value) {
            values.set(id, value);
        },
        async delete(id) {
            calls.deletes += 1;
            values.delete(id);
        },
        async withLock(_id, action) {
            calls.locks += 1;
            return action();
        },
    };
}

function jwt(payload) {
    return `x.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.y`;
}

async function loginConfig({ encrypted = true, expiresIn = 300 } = {}) {
    const backing = rawStore();
    const config = await createKeycloakBffAuth({
        clientId: "finder-client",
        issuer: "https://id.example.test/realms/test",
        secret: "unit-secret",
        tokenStore: backing,
        encryptTokenStore: encrypted,
    });
    const account = {
        access_token: jwt({
            realm_access: { roles: ["reader"] },
            resource_access: { "finder-client": { roles: ["editor"] } },
        }),
        refresh_token: jwt({ exp: Math.floor(Date.now() / 1000) + 3600 }),
        id_token: "id-token",
        expires_in: expiresIn,
    };
    const token = await config.callbacks.jwt({
        token: { sub: "user-1" },
        account,
    });
    return { backing, config, token, account };
}

beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(console, "error").mockImplementation(() => {});
    jest.spyOn(console, "info").mockImplementation(() => {});
    jest.spyOn(console, "debug").mockImplementation(() => {});
    getServerSessionMock.mockResolvedValue({
        expires: "future",
        userId: "user-1",
        user: { email: "user@example.test", name: "Unit User" },
        roles: ["reader", "editor"],
    });
});

test("createKeycloakBffAuth keeps OAuth tokens out of the browser JWT and encrypted at rest", async () => {
    const { backing, config, token, account } = await loginConfig();
    expect(token.bffSessionId).toEqual(expect.any(String));
    expect(token.accessToken).toBeUndefined();
    expect(token.refreshToken).toBeUndefined();
    expect(token.idToken).toBeUndefined();
    const persisted = backing.values.get(token.bffSessionId);
    expect(typeof persisted).toBe("string");
    expect(persisted).not.toContain(account.access_token);
    expect(config.session).toEqual(
        expect.objectContaining({ strategy: "jwt" }),
    );
    expect(keycloakProviderMock).toHaveBeenCalledWith(
        expect.objectContaining({ clientId: "finder-client" }),
    );
});

test("token-store encryption can be explicitly disabled", async () => {
    const { backing, token, account } = await loginConfig({ encrypted: false });
    expect(backing.values.get(token.bffSessionId)).toContain(
        account.access_token,
    );
});

test("session callback exposes roles and identity metadata but no OAuth tokens", async () => {
    const { config, token } = await loginConfig();
    const session = await config.callbacks.session({
        session: {
            expires: "future",
            user: { email: "user@example.test", name: "Unit" },
        },
        token,
    });
    expect(session.roles).toEqual(expect.arrayContaining(["reader", "editor"]));
    expect(session.accessToken).toBeUndefined();
    expect(session.refreshToken).toBeUndefined();
});

test("getAccessToken and requireAccessToken read only from the backend token store", async () => {
    const { config, token, account } = await loginConfig();
    getTokenMock.mockResolvedValue(token);
    expect(
        await getAccessToken(
            config,
            new NextRequest("http://localhost/api/test"),
        ),
    ).toBe(account.access_token);
    expect(
        await requireAccessToken(
            config,
            new NextRequest("http://localhost/api/test"),
        ),
    ).toBe(account.access_token);
});

test("missing backend session is surfaced as SESSION_EXPIRED", async () => {
    const { config, token, backing } = await loginConfig();
    backing.values.clear();
    getTokenMock.mockResolvedValue(token);
    await expect(
        getAccessToken(config, new NextRequest("http://localhost/api/test")),
    ).rejects.toMatchObject({
        code: "SESSION_EXPIRED",
        status: 401,
    });
});

test("anonymous request returns no optional token and required token throws 401", async () => {
    const { config } = await loginConfig();
    getTokenMock.mockResolvedValue(null);
    expect(
        await getAccessToken(
            config,
            new NextRequest("http://localhost/api/test"),
        ),
    ).toBeUndefined();
    await expect(
        requireAccessToken(
            config,
            new NextRequest("http://localhost/api/test"),
        ),
    ).rejects.toBeInstanceOf(BffUnauthorizedError);
});

test("getAuthenticatedUser returns backend roles without returning tokens", async () => {
    const { config, token } = await loginConfig();
    getTokenMock.mockResolvedValue(token);
    await expect(getAuthenticatedUser(config)).resolves.toEqual({
        id: "user-1",
        email: "user@example.test",
        name: "Unit User",
        roles: ["reader", "editor"],
    });
});

test("refresh is performed under the store lock and rotates backend tokens", async () => {
    const { backing, config, token } = await loginConfig({
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

    await config.callbacks.jwt({ token, account: null });

    expect(backing.calls.locks).toBeGreaterThan(0);
    const stored = JSON.parse(backing.values.get(token.bffSessionId));
    expect(stored.roles).toEqual(["refreshed"]);
    expect(stored.expiresAtEpochSec).toBeGreaterThan(
        Math.floor(Date.now() / 1000),
    );
});

test("rejected refresh deletes the backend session", async () => {
    const { backing, config, token } = await loginConfig({
        encrypted: false,
        expiresIn: -1,
    });
    globalThis.fetch = jest.fn(
        async () =>
            new Response(JSON.stringify({ error: "invalid_grant" }), {
                status: 400,
                headers: { "content-type": "application/json" },
            }),
    );

    const updated = await config.callbacks.jwt({ token, account: null });
    expect(updated.error).toBe("ReauthenticationRequired");
    expect(backing.values.has(token.bffSessionId)).toBe(false);
});

test("logout is idempotent, deletes backend state and clears auth cookies", async () => {
    const { backing, config, token } = await loginConfig({ encrypted: false });
    getTokenMock.mockResolvedValue(token);
    process.env.OIDC_AUTHORITY = "";
    process.env.OIDC_CLIENT_ID = "";
    const route = createLogoutRoute(async () => config);
    const request = new NextRequest(
        "http://localhost/api/auth/logout?callbackUrl=/profile",
        {
            method: "POST",
            headers: { cookie: "next-auth.session-token=abc; unrelated=keep" },
        },
    );
    const response = await route(request);
    expect(backing.values.has(token.bffSessionId)).toBe(false);
    expect(response.status).toBe(204);
    expect(response.headers.get("location")).toBeNull();
    expect(response.headers.get("set-cookie")).toContain(
        "next-auth.session-token=",
    );
});

test("logout returns 204 without a redirect", async () => {
    const { config } = await loginConfig({ encrypted: false });
    getTokenMock.mockResolvedValue(null);
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

test("BFF proxy sends the backend access token and preserves upstream status", async () => {
    const { config, token } = await loginConfig();
    getTokenMock.mockResolvedValue(token);
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
        new NextRequest("http://localhost/api/projects?q=one"),
        ["projects"],
    );
    expect(response.status).toBe(202);
    expect(response.headers.get("etag")).toBe("abc");
});
