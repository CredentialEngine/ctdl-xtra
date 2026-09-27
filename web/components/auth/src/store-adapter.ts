import {
    createCipheriv,
    createDecipheriv,
    createHash,
    randomBytes,
    randomUUID,
} from "node:crypto";
import type { RedisClient } from "@credentialengine/redis-client";
import type {
    Adapter,
    AdapterAccount,
    AdapterSession,
    AdapterUser,
    VerificationToken,
} from "next-auth/adapters";

const USER_PREFIX = "nextauth:user:";
const EMAIL_PREFIX = "nextauth:user-email:";
const ACCOUNT_PREFIX = "nextauth:account:";
const SESSION_PREFIX = "nextauth:session:";
const USER_ACCOUNTS_PREFIX = "nextauth:user-accounts:";
const VERIFICATION_PREFIX = "nextauth:verification:";
const SESSION_METADATA_PREFIX = "nextauth:session-metadata:";
const ENCRYPTED_VALUE_PREFIX = "enc:v1:";
const GCM_IV_LENGTH_BYTES = 12;
const GCM_AUTH_TAG_LENGTH_BYTES = 16;

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

export type RedisNextAuthStoreOptions = {
    redis: RedisClient;
    namespace: string;
    /** Encrypt OAuth token fields in Account rows before writing to Redis. */
    encryptTokens: boolean;
    /** Required when encryptTokens is true. Usually NEXTAUTH_SECRET. */
    encryptionSecret?: string;
};

export type RedisNextAuthStore = {
    adapter: Adapter;
    getAccount(
        provider: string,
        providerAccountId: string,
    ): Promise<AdapterAccount | undefined>;
    getAccountsForUser(userId: string): Promise<AdapterAccount[]>;
    upsertAccount(account: AdapterAccount): Promise<void>;
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

function parseUser(value: string | undefined): AdapterUser | null {
    if (!value) return null;
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

function parseSession(value: string | undefined): AdapterSession | null {
    if (!value) return null;
    const parsed = JSON.parse(value) as Omit<AdapterSession, "expires"> & {
        expires: string;
    };
    return { ...parsed, expires: new Date(parsed.expires) };
}

function parseVerificationToken(
    value: string | undefined,
): VerificationToken | null {
    if (!value) return null;
    const parsed = JSON.parse(value) as Omit<VerificationToken, "expires"> & {
        expires: string;
    };
    return { ...parsed, expires: new Date(parsed.expires) };
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
    return `${ENCRYPTED_VALUE_PREFIX}${iv.toString("base64url")}.${tag.toString("base64url")}.${ciphertext.toString("base64url")}`;
}

function decryptValue(value: string, key: Buffer): string {
    if (!value.startsWith(ENCRYPTED_VALUE_PREFIX)) return value;
    const payload = value.slice(ENCRYPTED_VALUE_PREFIX.length);
    const parts = payload.split(".");
    if (parts.length !== 3) {
        throw new Error("Invalid encrypted OAuth token field.");
    }
    const [ivPart, tagPart, ciphertextPart] = parts;
    const iv = Buffer.from(ivPart, "base64url");
    const tag = Buffer.from(tagPart, "base64url");
    if (
        iv.length !== GCM_IV_LENGTH_BYTES ||
        tag.length !== GCM_AUTH_TAG_LENGTH_BYTES
    ) {
        throw new Error("Invalid encrypted OAuth token field.");
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

function protectAccount(
    account: AdapterAccount,
    encryptionKey: Buffer | undefined,
): AdapterAccount {
    if (!encryptionKey) return { ...account };
    return {
        ...account,
        access_token:
            typeof account.access_token === "string" && account.access_token
                ? encryptValue(account.access_token, encryptionKey)
                : account.access_token,
        refresh_token:
            typeof account.refresh_token === "string" && account.refresh_token
                ? encryptValue(account.refresh_token, encryptionKey)
                : account.refresh_token,
        id_token:
            typeof account.id_token === "string" && account.id_token
                ? encryptValue(account.id_token, encryptionKey)
                : account.id_token,
    };
}

function unprotectAccount(
    account: AdapterAccount,
    decryptionKey: Buffer | undefined,
): AdapterAccount {
    if (!decryptionKey) return { ...account };
    return {
        ...account,
        access_token:
            typeof account.access_token === "string" && account.access_token
                ? decryptValue(account.access_token, decryptionKey)
                : account.access_token,
        refresh_token:
            typeof account.refresh_token === "string" && account.refresh_token
                ? decryptValue(account.refresh_token, decryptionKey)
                : account.refresh_token,
        id_token:
            typeof account.id_token === "string" && account.id_token
                ? decryptValue(account.id_token, decryptionKey)
                : account.id_token,
    };
}

function sleep(milliseconds: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

/**
 * Standard NextAuth v4 Adapter backed directly by Redis. User, Account and
 * Session are the canonical NextAuth records. OAuth token fields live on the
 * Account row and may optionally be encrypted before persistence.
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
        user: (id: string) => `${namespace}:${USER_PREFIX}${encodeKeyPart(id)}`,
        email: (email: string) =>
            `${namespace}:${EMAIL_PREFIX}${encodeKeyPart(email.trim().toLowerCase())}`,
        account: (provider: string, providerAccountId: string) =>
            `${namespace}:${ACCOUNT_PREFIX}${encodeKeyPart(provider)}:${encodeKeyPart(providerAccountId)}`,
        session: (sessionToken: string) =>
            `${namespace}:${SESSION_PREFIX}${encodeKeyPart(sessionToken)}`,
        userAccounts: (userId: string) =>
            `${namespace}:${USER_ACCOUNTS_PREFIX}${encodeKeyPart(userId)}`,
        verification: (identifier: string, token: string) =>
            `${namespace}:${VERIFICATION_PREFIX}${encodeKeyPart(identifier)}:${encodeKeyPart(token)}`,
        sessionMetadata: (sessionToken: string) =>
            `${namespace}:${SESSION_METADATA_PREFIX}${encodeKeyPart(sessionToken)}`,
        lock: (name: string) =>
            `${namespace}:nextauth:lock:${encodeKeyPart(name)}`,
    };

    async function getAccount(
        provider: string,
        providerAccountId: string,
    ): Promise<AdapterAccount | undefined> {
        const raw = await redis.get(key.account(provider, providerAccountId));
        if (!raw) return undefined;
        return unprotectAccount(
            JSON.parse(raw) as AdapterAccount,
            decryptionKey,
        );
    }

    async function writeAccount(account: AdapterAccount): Promise<void> {
        const persisted = protectAccount(account, encryptionKey);
        const accountKey = key.account(
            account.provider,
            account.providerAccountId,
        );
        const existingTtl = await redis.ttl(accountKey);
        await redis.set(accountKey, serialize(persisted));
        if (existingTtl > 0) {
            await redis.expire(accountKey, existingTtl);
        }

        const refsRaw = await redis.get(key.userAccounts(account.userId));
        const refs = refsRaw ? (JSON.parse(refsRaw) as LinkedAccountRef[]) : [];
        if (
            !refs.some(
                (ref) =>
                    ref.provider === account.provider &&
                    ref.providerAccountId === account.providerAccountId,
            )
        ) {
            refs.push({
                provider: account.provider,
                providerAccountId: account.providerAccountId,
            });
            await redis.set(key.userAccounts(account.userId), serialize(refs));
        }
    }

    async function getAccountsForUser(
        userId: string,
    ): Promise<AdapterAccount[]> {
        const refsRaw = await redis.get(key.userAccounts(userId));
        if (!refsRaw) return [];
        const refs = JSON.parse(refsRaw) as LinkedAccountRef[];
        const accounts = await Promise.all(
            refs.map((ref) => getAccount(ref.provider, ref.providerAccountId)),
        );
        return accounts.filter((account): account is AdapterAccount =>
            Boolean(account),
        );
    }

    async function getAccountRefsForUser(
        userId: string,
    ): Promise<LinkedAccountRef[]> {
        const refsRaw = await redis.get(key.userAccounts(userId));
        return refsRaw ? (JSON.parse(refsRaw) as LinkedAccountRef[]) : [];
    }

    async function deleteAuthStateForUser(userId: string): Promise<void> {
        const user = parseUser(await redis.get(key.user(userId)));
        const refs = await getAccountRefsForUser(userId);
        const keys = [
            key.user(userId),
            key.userAccounts(userId),
            ...refs.map((ref) =>
                key.account(ref.provider, ref.providerAccountId),
            ),
        ];
        if (user?.email) keys.push(key.email(user.email));
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
            ...refs.map((ref) =>
                key.account(ref.provider, ref.providerAccountId),
            ),
        ];
        if (user?.email) keys.push(key.email(user.email));
        await Promise.all(
            keys.map((authKey) => redis.expire(authKey, ttlSeconds)),
        );
    }

    const adapter: Adapter = {
        async createUser(user: CreateUserInput) {
            const created: AdapterUser = { ...user, id: randomUUID() };
            await redis.set(key.user(created.id), serialize(created));
            if (created.email) {
                await redis.set(key.email(created.email), created.id);
            }
            return created;
        },

        async getUser(id) {
            return parseUser(await redis.get(key.user(id)));
        },

        async getUserByEmail(email) {
            const id = await redis.get(key.email(email));
            return id ? parseUser(await redis.get(key.user(id))) : null;
        },

        async getUserByAccount({ provider, providerAccountId }) {
            const account = await getAccount(provider, providerAccountId);
            if (account) {
                return parseUser(await redis.get(key.user(account.userId)));
            }

            return null;
        },

        async updateUser(update) {
            const existing = parseUser(await redis.get(key.user(update.id)));
            if (!existing) {
                throw new Error(`NextAuth user ${update.id} does not exist.`);
            }
            const updated: AdapterUser = { ...existing, ...update };
            await redis.set(key.user(updated.id), serialize(updated));

            if (
                existing.email &&
                existing.email.toLowerCase() !== updated.email?.toLowerCase()
            ) {
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
            return account;
        },

        async unlinkAccount({
            provider,
            providerAccountId,
        }: UnlinkAccountInput) {
            const existing = await getAccount(provider, providerAccountId);
            const userId = existing?.userId;

            await redis.del(key.account(provider, providerAccountId));
            if (!userId) return;

            const refsRaw = await redis.get(key.userAccounts(userId));
            if (!refsRaw) return;
            const refs = (JSON.parse(refsRaw) as LinkedAccountRef[]).filter(
                (ref) =>
                    ref.provider !== provider ||
                    ref.providerAccountId !== providerAccountId,
            );
            if (refs.length) {
                await redis.set(key.userAccounts(userId), serialize(refs));
            } else {
                await redis.del(key.userAccounts(userId));
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
            return session;
        },

        async getSessionAndUser(sessionToken) {
            const session = parseSession(
                await redis.get(key.session(sessionToken)),
            );
            if (!session) return null;
            if (session.expires.getTime() <= Date.now()) {
                await Promise.all([
                    redis.del(key.session(sessionToken)),
                    redis.del(key.sessionMetadata(sessionToken)),
                    deleteAuthStateForUser(session.userId),
                ]);
                return null;
            }
            const user = parseUser(await redis.get(key.user(session.userId)));
            return user ? { session, user } : null;
        },

        async updateSession(update) {
            const existing = parseSession(
                await redis.get(key.session(update.sessionToken)),
            );
            if (!existing) return null;
            const updated: AdapterSession = { ...existing, ...update };
            const ttlSeconds = ttlUntil(updated.expires);
            await redis.set(
                key.session(updated.sessionToken),
                serialize(updated),
                { EX: ttlSeconds },
            );
            await expireAuthStateForUser(updated.userId, ttlSeconds);
            const metadata = await redis.get(
                key.sessionMetadata(updated.sessionToken),
            );
            if (metadata) {
                await redis.set(
                    key.sessionMetadata(updated.sessionToken),
                    metadata,
                    { EX: ttlUntil(updated.expires) },
                );
            }
            return updated;
        },

        async deleteSession(sessionToken) {
            const existing = parseSession(
                await redis.get(key.session(sessionToken)),
            );
            await Promise.all([
                redis.del(key.session(sessionToken)),
                redis.del(key.sessionMetadata(sessionToken)),
                ...(existing ? [deleteAuthStateForUser(existing.userId)] : []),
            ]);
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
            if (!existing) return null;
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
                        { keys: [lockKey], arguments: [owner] },
                    );
                }
            }
            await sleep(50);
        }
        throw new Error(`Timed out waiting for auth lock: ${name}`);
    }

    return {
        adapter,
        getAccount,
        getAccountsForUser,
        upsertAccount: writeAccount,
        async getSessionMetadata(sessionToken) {
            const raw = await redis.get(key.sessionMetadata(sessionToken));
            return raw ? (JSON.parse(raw) as DatabaseSessionMetadata) : {};
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
