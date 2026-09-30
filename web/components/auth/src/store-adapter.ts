import type { RedisClient } from "@credentialengine/redis-client";
import type {
    Adapter,
    AdapterAccount,
    AdapterSession,
    AdapterUser,
    VerificationToken,
} from "next-auth/adapters";
import {
    createCipheriv,
    createDecipheriv,
    createHash,
    randomBytes,
    randomUUID,
} from "node:crypto";

const USER_PREFIX = "nextauth:user:";
const EMAIL_PREFIX = "nextauth:user-email:";
const ACCOUNT_PREFIX = "nextauth:account:";
const SESSION_PREFIX = "nextauth:session:";
const SESSION_TOKENS_PREFIX = "nextauth:session-tokens:";
const PENDING_TOKENS_PREFIX = "nextauth:pending-tokens:";
const USER_ACCOUNTS_PREFIX = "nextauth:user-accounts:";
const VERIFICATION_PREFIX = "nextauth:verification:";
const SESSION_METADATA_PREFIX = "nextauth:session-metadata:";
const ENCRYPTED_VALUE_PREFIX = "enc:v1:";
const GCM_IV_LENGTH_BYTES = 12;
const GCM_AUTH_TAG_LENGTH_BYTES = 16;

const PENDING_TOKENS_TTL_SECONDS = 60;

type CreateUserInput = Parameters<NonNullable<Adapter["createUser"]>>[0];
type LinkAccountInput = Parameters<NonNullable<Adapter["linkAccount"]>>[0];
type UnlinkAccountInput = Parameters<NonNullable<Adapter["unlinkAccount"]>>[0];

export type LinkedAccountRef = Pick<
    AdapterAccount,
    "provider" | "providerAccountId"
>;

export type DatabaseSessionMetadata = {
    activeTenantId?: string;
};

export type SessionTokens = {
    provider: string;
    providerAccountId: string;
    accessToken: string;
    refreshToken?: string;
    idToken?: string;
    expiresAtEpochSec: number;
};

export type RedisNextAuthStoreOptions = {
    redis: RedisClient;
    namespace: string;
    /** Encrypt OAuth tokens before writing them to Redis. */
    encryptTokens: boolean;
    /** Required when encryptTokens is true. Usually NEXTAUTH_SECRET. */
    encryptionSecret?: string;
};

export type RedisNextAuthStore = {
    adapter: Adapter;
    stashLoginTokens(tokens: SessionTokens): Promise<void>;
    getSessionTokens(sessionToken: string): Promise<SessionTokens | undefined>;
    setSessionTokens(
        sessionToken: string,
        tokens: SessionTokens,
    ): Promise<void>;
    getSessionMetadata(sessionToken: string): Promise<DatabaseSessionMetadata>;
    setSessionMetadata(
        sessionToken: string,
        metadata: DatabaseSessionMetadata,
        expiresAt: Date,
    ): Promise<void>;
    deleteSessionMetadata(sessionToken: string): Promise<void>;
    withLock<T>(name: string, action: () => Promise<T>): Promise<T>;
};

function encodeKeyPart(value: string): string {
    return encodeURIComponent(value);
}

function serialize(value: unknown): string {
    return JSON.stringify(value);
}

function parseUser(value: string | undefined): AdapterUser | undefined {
    if (!value) {
        return undefined;
    }
    const parsed = JSON.parse(value) as Omit<AdapterUser, "emailVerified"> & {
        emailVerified: string | null;
    };
    return {
        ...parsed,
        emailVerified: parsed.emailVerified
            ? new Date(parsed.emailVerified)
            : null,
    };
}

function parseSession(value: string | undefined): AdapterSession | undefined {
    if (!value) {
        return undefined;
    }
    const parsed = JSON.parse(value) as Omit<AdapterSession, "expires"> & {
        expires: string;
    };
    return {
        ...parsed,
        expires: new Date(parsed.expires),
    };
}

function parseVerificationToken(
    value: string | undefined,
): VerificationToken | undefined {
    if (!value) {
        return undefined;
    }
    const parsed = JSON.parse(value) as Omit<VerificationToken, "expires"> & {
        expires: string;
    };
    return {
        ...parsed,
        expires: new Date(parsed.expires),
    };
}

function ttlUntil(expires: Date): number {
    return Math.max(1, Math.ceil((expires.getTime() - Date.now()) / 1000));
}

function deriveEncryptionKey(secret: string): Buffer {
    if (!secret.trim()) {
        throw new Error("A non-empty token encryption secret is required.");
    }
    return createHash("sha256")
        .update("credentialengine:nextauth:oauth-token-fields:v1\0")
        .update(secret)
        .digest();
}

function encryptValue(value: string, key: Buffer): string {
    const iv = randomBytes(GCM_IV_LENGTH_BYTES);
    const cipher = createCipheriv("aes-256-gcm", key, iv, {
        authTagLength: GCM_AUTH_TAG_LENGTH_BYTES,
    });
    const ciphertext = Buffer.concat([
        cipher.update(value, "utf8"),
        cipher.final(),
    ]);
    const tag = cipher.getAuthTag();
    const parts = [
        iv.toString("base64url"),
        tag.toString("base64url"),
        ciphertext.toString("base64url"),
    ];
    return `${ENCRYPTED_VALUE_PREFIX}${parts.join(".")}`;
}

function decryptValue(value: string, key: Buffer): string {
    const payload = value.slice(ENCRYPTED_VALUE_PREFIX.length);
    const parts = payload.split(".");
    if (parts.length !== 3) {
        throw new Error("Invalid encrypted auth value.");
    }
    const [ivPart, tagPart, ciphertextPart] = parts;
    const iv = Buffer.from(ivPart, "base64url");
    const tag = Buffer.from(tagPart, "base64url");
    if (
        iv.length !== GCM_IV_LENGTH_BYTES ||
        tag.length !== GCM_AUTH_TAG_LENGTH_BYTES
    ) {
        throw new Error("Invalid encrypted auth value.");
    }
    const decipher = createDecipheriv("aes-256-gcm", key, iv, {
        authTagLength: GCM_AUTH_TAG_LENGTH_BYTES,
    });
    decipher.setAuthTag(tag);
    return Buffer.concat([
        decipher.update(Buffer.from(ciphertextPart, "base64url")),
        decipher.final(),
    ]).toString("utf8");
}

function accountLink(account: AdapterAccount): AdapterAccount {
    return {
        userId: account.userId,
        type: account.type,
        provider: account.provider,
        providerAccountId: account.providerAccountId,
    };
}

function hasTokenFields(account: AdapterAccount): boolean {
    return (
        account.access_token !== undefined ||
        account.refresh_token !== undefined ||
        account.id_token !== undefined
    );
}

function sleep(milliseconds: number): Promise<void> {
    return new Promise((resolve) => {
        setTimeout(resolve, milliseconds);
    });
}

/**
 * NextAuth v4 Adapter backed directly by Redis.
 *
 * User and Account records are per person. OAuth tokens are per login: each
 * NextAuth database session has its own token record, so logging out or
 * refreshing on one device does not touch the user's other devices.
 */
export function createRedisNextAuthStore(
    options: RedisNextAuthStoreOptions,
): RedisNextAuthStore {
    const { redis } = options;
    const namespace = options.namespace.trim().replace(/:+$/, "");
    if (!namespace) {
        throw new Error("Redis auth namespace is required.");
    }
    const decryptionKey = options.encryptionSecret
        ? deriveEncryptionKey(options.encryptionSecret)
        : undefined;
    const encryptionKey = options.encryptTokens ? decryptionKey : undefined;
    if (options.encryptTokens && !encryptionKey) {
        throw new Error(
            "Token encryption is enabled but no encryption secret was provided.",
        );
    }

    const key = {
        user: (id: string) => {
            return `${namespace}:${USER_PREFIX}${encodeKeyPart(id)}`;
        },
        email: (email: string) => {
            const normalized = email.trim().toLowerCase();
            return `${namespace}:${EMAIL_PREFIX}${encodeKeyPart(normalized)}`;
        },
        account: (provider: string, providerAccountId: string) => {
            return [
                `${namespace}:${ACCOUNT_PREFIX}${encodeKeyPart(provider)}`,
                encodeKeyPart(providerAccountId),
            ].join(":");
        },
        session: (sessionToken: string) => {
            return `${namespace}:${SESSION_PREFIX}${encodeKeyPart(sessionToken)}`;
        },
        sessionTokens: (sessionToken: string) => {
            return [
                `${namespace}:${SESSION_TOKENS_PREFIX}`,
                encodeKeyPart(sessionToken),
            ].join("");
        },
        pendingTokens: (provider: string, providerAccountId: string) => {
            return [
                `${namespace}:${PENDING_TOKENS_PREFIX}${encodeKeyPart(provider)}`,
                encodeKeyPart(providerAccountId),
            ].join(":");
        },
        userAccounts: (userId: string) => {
            return `${namespace}:${USER_ACCOUNTS_PREFIX}${encodeKeyPart(userId)}`;
        },
        verification: (identifier: string, token: string) => {
            return [
                `${namespace}:${VERIFICATION_PREFIX}${encodeKeyPart(identifier)}`,
                encodeKeyPart(token),
            ].join(":");
        },
        sessionMetadata: (sessionToken: string) => {
            return [
                `${namespace}:${SESSION_METADATA_PREFIX}`,
                encodeKeyPart(sessionToken),
            ].join("");
        },
        lock: (name: string) => {
            return `${namespace}:nextauth:lock:${encodeKeyPart(name)}`;
        },
    };

    function protect(value: string): string {
        if (!encryptionKey) {
            return value;
        }
        return encryptValue(value, encryptionKey);
    }

    function unprotect(value: string): string {
        if (!value.startsWith(ENCRYPTED_VALUE_PREFIX)) {
            return value;
        }
        if (!decryptionKey) {
            throw new Error(
                "Encrypted auth state found but no encryption secret is configured.",
            );
        }
        return decryptValue(value, decryptionKey);
    }

    function parseTokens(raw: string): SessionTokens {
        return JSON.parse(unprotect(raw)) as SessionTokens;
    }

    async function getAccount(
        provider: string,
        providerAccountId: string,
    ): Promise<AdapterAccount | undefined> {
        const raw = await redis.get(key.account(provider, providerAccountId));
        if (!raw) {
            return undefined;
        }
        return JSON.parse(raw) as AdapterAccount;
    }

    async function getAccountRefsForUser(
        userId: string,
    ): Promise<LinkedAccountRef[]> {
        const refsRaw = await redis.get(key.userAccounts(userId));
        if (!refsRaw) {
            return [];
        }
        return JSON.parse(refsRaw) as LinkedAccountRef[];
    }

    async function writeAccount(account: AdapterAccount): Promise<void> {
        const link = accountLink(account);
        const accountKey = key.account(link.provider, link.providerAccountId);
        const existingTtl = await redis.ttl(accountKey);
        await redis.set(accountKey, serialize(link));
        if (existingTtl > 0) {
            await redis.expire(accountKey, existingTtl);
        }

        const refs = await getAccountRefsForUser(link.userId);
        const alreadyLinked = refs.some((ref) => {
            return (
                ref.provider === link.provider &&
                ref.providerAccountId === link.providerAccountId
            );
        });
        if (!alreadyLinked) {
            refs.push({
                provider: link.provider,
                providerAccountId: link.providerAccountId,
            });
            await redis.set(key.userAccounts(link.userId), serialize(refs));
        }
    }

    /** Only used by deleteUser. Logout and expiry never remove the user. */
    async function deleteAuthStateForUser(userId: string): Promise<void> {
        const user = parseUser(await redis.get(key.user(userId)));
        const refs = await getAccountRefsForUser(userId);
        const keys = [
            key.user(userId),
            key.userAccounts(userId),
            ...refs.map((ref) => {
                return key.account(ref.provider, ref.providerAccountId);
            }),
        ];
        if (user?.email) {
            keys.push(key.email(user.email));
        }
        await redis.del(...keys);
    }

    async function expireAuthStateForUser(
        userId: string,
        ttlSeconds: number,
    ): Promise<void> {
        const user = parseUser(await redis.get(key.user(userId)));
        const refs = await getAccountRefsForUser(userId);
        const keys = [
            key.user(userId),
            key.userAccounts(userId),
            ...refs.map((ref) => {
                return key.account(ref.provider, ref.providerAccountId);
            }),
        ];
        if (user?.email) {
            keys.push(key.email(user.email));
        }
        await Promise.all(
            keys.map((authKey) => {
                return redis.expire(authKey, ttlSeconds);
            }),
        );
    }

    async function claimPendingTokens(
        userId: string,
    ): Promise<SessionTokens | undefined> {
        const refs = await getAccountRefsForUser(userId);
        for (const ref of refs) {
            const pendingKey = key.pendingTokens(
                ref.provider,
                ref.providerAccountId,
            );
            const raw = await redis.get(pendingKey);
            if (raw) {
                await redis.del(pendingKey);
                return parseTokens(raw);
            }
        }
        return undefined;
    }

    async function deleteSessionState(sessionToken: string): Promise<void> {
        await redis.del(
            key.session(sessionToken),
            key.sessionTokens(sessionToken),
            key.sessionMetadata(sessionToken),
        );
    }

    async function stashLoginTokens(tokens: SessionTokens): Promise<void> {
        await redis.set(
            key.pendingTokens(tokens.provider, tokens.providerAccountId),
            protect(serialize(tokens)),
            { EX: PENDING_TOKENS_TTL_SECONDS },
        );

        const existing = await getAccount(
            tokens.provider,
            tokens.providerAccountId,
        );
        if (existing && hasTokenFields(existing)) {
            await writeAccount(existing);
        }
    }

    async function getSessionTokens(
        sessionToken: string,
    ): Promise<SessionTokens | undefined> {
        const raw = await redis.get(key.sessionTokens(sessionToken));
        if (!raw) {
            return undefined;
        }
        return parseTokens(raw);
    }

    async function setSessionTokens(
        sessionToken: string,
        tokens: SessionTokens,
    ): Promise<void> {
        const sessionTtl = await redis.ttl(key.session(sessionToken));
        if (sessionTtl === -2) {
            return;
        }
        const tokensKey = key.sessionTokens(sessionToken);
        const value = protect(serialize(tokens));
        if (sessionTtl > 0) {
            await redis.set(tokensKey, value, { EX: sessionTtl });
        } else {
            await redis.set(tokensKey, value);
        }
    }

    const adapter: Adapter = {
        async createUser(user: CreateUserInput) {
            const created: AdapterUser = {
                ...user,
                id: randomUUID(),
            };
            await redis.set(key.user(created.id), serialize(created));
            if (created.email) {
                await redis.set(key.email(created.email), created.id);
            }
            return created;
        },

        async getUser(id) {
            const user = parseUser(await redis.get(key.user(id)));
            return user ?? null;
        },

        async getUserByEmail(email) {
            const id = await redis.get(key.email(email));
            if (!id) {
                return null;
            }
            const user = parseUser(await redis.get(key.user(id)));
            return user ?? null;
        },

        async getUserByAccount({ provider, providerAccountId }) {
            const account = await getAccount(provider, providerAccountId);
            if (!account) {
                return null;
            }
            const user = parseUser(await redis.get(key.user(account.userId)));
            return user ?? null;
        },

        async updateUser(update) {
            const existing = parseUser(await redis.get(key.user(update.id)));
            if (!existing) {
                throw new Error(`NextAuth user ${update.id} does not exist.`);
            }
            const updated: AdapterUser = {
                ...existing,
                ...update,
            };
            await redis.set(key.user(updated.id), serialize(updated));

            const emailChanged =
                existing.email &&
                existing.email.toLowerCase() !== updated.email?.toLowerCase();
            if (emailChanged) {
                await redis.del(key.email(existing.email));
            }
            if (updated.email) {
                await redis.set(key.email(updated.email), updated.id);
            }
            return updated;
        },

        async deleteUser(userId) {
            await deleteAuthStateForUser(userId);
        },

        async linkAccount(account: LinkAccountInput) {
            await writeAccount(account);
            return accountLink(account);
        },

        async unlinkAccount({
            provider,
            providerAccountId,
        }: UnlinkAccountInput) {
            const existing = await getAccount(provider, providerAccountId);
            await redis.del(key.account(provider, providerAccountId));
            if (!existing) {
                return;
            }

            const refs = (await getAccountRefsForUser(existing.userId)).filter(
                (ref) => {
                    return (
                        ref.provider !== provider ||
                        ref.providerAccountId !== providerAccountId
                    );
                },
            );
            if (refs.length > 0) {
                await redis.set(
                    key.userAccounts(existing.userId),
                    serialize(refs),
                );
            } else {
                await redis.del(key.userAccounts(existing.userId));
            }
        },

        async createSession(session) {
            const ttlSeconds = ttlUntil(session.expires);
            await redis.set(
                key.session(session.sessionToken),
                serialize(session),
                { EX: ttlSeconds },
            );
            await expireAuthStateForUser(session.userId, ttlSeconds);

            const tokens = await claimPendingTokens(session.userId);
            if (tokens) {
                await redis.set(
                    key.sessionTokens(session.sessionToken),
                    protect(serialize(tokens)),
                    { EX: ttlSeconds },
                );
            } else {
                console.warn(
                    "[auth] New session has no login tokens to attach",
                    { userId: session.userId },
                );
            }
            return session;
        },

        async getSessionAndUser(sessionToken) {
            const session = parseSession(
                await redis.get(key.session(sessionToken)),
            );
            if (!session) {
                return null;
            }
            if (session.expires.getTime() <= Date.now()) {
                await deleteSessionState(sessionToken);
                return null;
            }
            const user = parseUser(await redis.get(key.user(session.userId)));
            if (!user) {
                return null;
            }
            return {
                session,
                user,
            };
        },

        async updateSession(update) {
            const existing = parseSession(
                await redis.get(key.session(update.sessionToken)),
            );
            if (!existing) {
                return undefined;
            }
            const updated: AdapterSession = {
                ...existing,
                ...update,
            };
            const ttlSeconds = ttlUntil(updated.expires);
            await redis.set(
                key.session(updated.sessionToken),
                serialize(updated),
                { EX: ttlSeconds },
            );
            await Promise.all([
                redis.expire(
                    key.sessionTokens(updated.sessionToken),
                    ttlSeconds,
                ),
                redis.expire(
                    key.sessionMetadata(updated.sessionToken),
                    ttlSeconds,
                ),
                expireAuthStateForUser(updated.userId, ttlSeconds),
            ]);
            return updated;
        },

        async deleteSession(sessionToken) {
            const existing = parseSession(
                await redis.get(key.session(sessionToken)),
            );
            await deleteSessionState(sessionToken);
            return existing;
        },

        async createVerificationToken(token) {
            await redis.set(
                key.verification(token.identifier, token.token),
                serialize(token),
                { EX: ttlUntil(token.expires) },
            );
            return token;
        },

        async useVerificationToken({ identifier, token }) {
            const tokenKey = key.verification(identifier, token);
            const existing = parseVerificationToken(await redis.get(tokenKey));
            if (!existing) {
                return null;
            }
            await redis.del(tokenKey);
            return existing;
        },
    };

    async function withLock<T>(
        name: string,
        action: () => Promise<T>,
    ): Promise<T> {
        const lockKey = key.lock(name);
        const owner = randomUUID();
        const deadline = Date.now() + 10_000;
        while (Date.now() < deadline) {
            const acquired = await redis.set(lockKey, owner, {
                NX: true,
                PX: 30_000,
            });
            if (acquired) {
                try {
                    return await action();
                } finally {
                    await redis.eval(
                        "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                        {
                            keys: [lockKey],
                            arguments: [owner],
                        },
                    );
                }
            }
            await sleep(50);
        }
        throw new Error(`Timed out waiting for auth lock: ${name}`);
    }

    return {
        adapter,
        stashLoginTokens,
        getSessionTokens,
        setSessionTokens,
        async getSessionMetadata(sessionToken) {
            const raw = await redis.get(key.sessionMetadata(sessionToken));
            if (!raw) {
                return {};
            }
            return JSON.parse(raw) as DatabaseSessionMetadata;
        },
        async setSessionMetadata(sessionToken, metadata, expiresAt) {
            await redis.set(
                key.sessionMetadata(sessionToken),
                serialize(metadata),
                { EX: ttlUntil(expiresAt) },
            );
        },
        async deleteSessionMetadata(sessionToken) {
            await redis.del(key.sessionMetadata(sessionToken));
        },
        withLock,
    };
}
