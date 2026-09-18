import { RedisClient, createRedisClient } from "@credentialengine/redis-client";
import {
    createCipheriv,
    createDecipheriv,
    createHash,
    randomBytes,
    randomUUID,
} from "node:crypto";

export interface ServerSessionStore<T> {
    get(sessionId: string): Promise<T | undefined>;
    set(sessionId: string, value: T, ttlSeconds: number): Promise<void>;
    delete(sessionId: string): Promise<void>;
    withLock<R>(sessionId: string, action: () => Promise<R>): Promise<R>;
}

export type EncryptedServerSessionStoreOptions = {
    /**
     * Server-only secret used to derive the AES-256-GCM key. This must never be
     * exposed to the browser. The auth package uses the resolved NextAuth secret.
     */
    secret: string;
    /** Stable purpose string so the same secret is not reused directly as a key. */
    purpose?: string;
};

type EncryptedEnvelope = {
    v: 1;
    iv: string;
    tag: string;
    ciphertext: string;
};

function deriveEncryptionKey(secret: string, purpose: string): Buffer {
    if (!secret) {
        throw new Error(
            "A non-empty server-session encryption secret is required.",
        );
    }

    return createHash("sha256")
        .update("credentialengine:server-session:aes-256-gcm:v1\0")
        .update(purpose)
        .update("\0")
        .update(secret)
        .digest();
}

function encryptValue<T>(value: T, key: Buffer): string {
    const iv = randomBytes(12);

    const cipher = createCipheriv("aes-256-gcm", key, iv, {
        authTagLength: 16,
    });

    const plaintext = Buffer.from(JSON.stringify(value), "utf8");

    const ciphertext = Buffer.concat([
        cipher.update(plaintext),
        cipher.final(),
    ]);

    const tag = cipher.getAuthTag();

    if (tag.length !== 16) {
        throw new Error("Unexpected AES-GCM authentication tag length.");
    }

    const envelope: EncryptedEnvelope = {
        v: 1,
        iv: iv.toString("base64url"),
        tag: tag.toString("base64url"),
        ciphertext: ciphertext.toString("base64url"),
    };

    return JSON.stringify(envelope);
}

function decryptValue<T>(serialized: string, key: Buffer): T {
    let envelope: EncryptedEnvelope;

    try {
        envelope = JSON.parse(serialized) as EncryptedEnvelope;
    } catch {
        throw new Error(
            "Server-session payload is not a valid encrypted envelope.",
        );
    }

    if (
        envelope.v !== 1 ||
        !envelope.iv ||
        !envelope.tag ||
        !envelope.ciphertext
    ) {
        throw new Error(
            "Server-session payload is not encrypted with the supported format.",
        );
    }

    try {
        const iv = Buffer.from(envelope.iv, "base64url");

        const tag = Buffer.from(envelope.tag, "base64url");

        const ciphertext = Buffer.from(envelope.ciphertext, "base64url");

        if (iv.length !== 12) {
            throw new Error("Invalid AES-GCM IV length.");
        }

        if (tag.length !== 16) {
            throw new Error("Invalid AES-GCM authentication tag length.");
        }

        const decipher = createDecipheriv("aes-256-gcm", key, iv, {
            authTagLength: 16,
        });

        decipher.setAuthTag(tag);

        const plaintext = Buffer.concat([
            decipher.update(ciphertext),
            decipher.final(),
        ]);

        return JSON.parse(plaintext.toString("utf8")) as T;
    } catch {
        throw new Error(
            "Unable to decrypt server-session payload. Check the backend auth secret.",
        );
    }
}

/**
 * Encrypts every value before it reaches the backing store. Session IDs and TTLs
 * remain available to the backing store, but OAuth token material is ciphertext.
 */
export function createEncryptedServerSessionStore<T>(
    backingStore: ServerSessionStore<string>,
    options: EncryptedServerSessionStoreOptions,
): ServerSessionStore<T> {
    const purpose = options.purpose ?? "default";

    const key = deriveEncryptionKey(options.secret, purpose);

    return {
        async get(sessionId) {
            const encrypted = await backingStore.get(sessionId);

            if (!encrypted) {
                return undefined;
            }

            return decryptValue<T>(encrypted, key);
        },

        async set(sessionId, value, ttlSeconds) {
            await backingStore.set(
                sessionId,
                encryptValue(value, key),
                ttlSeconds,
            );
        },

        delete(sessionId) {
            return backingStore.delete(sessionId);
        },

        withLock(sessionId, action) {
            return backingStore.withLock(sessionId, action);
        },
    };
}

/**
 * Serializes session values as plain JSON before passing them to the string
 * backing store. Use only when server-session encryption is explicitly disabled.
 */
export function createJsonServerSessionStore<T>(
    backingStore: ServerSessionStore<string>,
): ServerSessionStore<T> {
    return {
        async get(sessionId) {
            const serialized = await backingStore.get(sessionId);

            if (!serialized) {
                return undefined;
            }

            return JSON.parse(serialized) as T;
        },

        async set(sessionId, value, ttlSeconds) {
            await backingStore.set(
                sessionId,
                JSON.stringify(value),
                ttlSeconds,
            );
        },

        delete(sessionId) {
            return backingStore.delete(sessionId);
        },

        withLock(sessionId, action) {
            return backingStore.withLock(sessionId, action);
        },
    };
}

export type MemoryServerSessionStoreOptions = {
    namespace?: string;
};

type MemoryEntry<T> = {
    value: T;
    expiresAt: number;
};

type MemoryGlobal = typeof globalThis & {
    __credentialEngineServerSessionStores?: Map<
        string,
        Map<string, MemoryEntry<unknown>>
    >;

    __credentialEngineServerSessionLocks?: Map<string, Promise<void>>;
};

function memoryStores() {
    const globalObject = globalThis as MemoryGlobal;

    globalObject.__credentialEngineServerSessionStores ??= new Map();

    return globalObject.__credentialEngineServerSessionStores;
}

function memoryLocks() {
    const globalObject = globalThis as MemoryGlobal;

    globalObject.__credentialEngineServerSessionLocks ??= new Map();

    return globalObject.__credentialEngineServerSessionLocks;
}

export function createMemoryServerSessionStore<T>(
    options: MemoryServerSessionStoreOptions = {},
): ServerSessionStore<T> {
    const namespace = options.namespace ?? "default";

    const stores = memoryStores();

    let rawStore = stores.get(namespace);

    if (!rawStore) {
        rawStore = new Map<string, MemoryEntry<unknown>>();

        stores.set(namespace, rawStore);
    }

    const values = rawStore as Map<string, MemoryEntry<T>>;

    const locks = memoryLocks();

    return {
        async get(sessionId) {
            const entry = values.get(sessionId);

            if (!entry) {
                return undefined;
            }

            if (entry.expiresAt <= Date.now()) {
                values.delete(sessionId);

                return undefined;
            }

            return entry.value;
        },

        async set(sessionId, value, ttlSeconds) {
            values.set(sessionId, {
                value,
                expiresAt: Date.now() + Math.max(1, ttlSeconds) * 1000,
            });
        },

        async delete(sessionId) {
            values.delete(sessionId);
        },

        async withLock<R>(
            sessionId: string,
            action: () => Promise<R>,
        ): Promise<R> {
            const lockKey = `${namespace}:${sessionId}`;

            const previous = locks.get(lockKey) ?? Promise.resolve();

            let release!: () => void;

            const current = new Promise<void>((resolve) => {
                release = resolve;
            });

            const queued = previous.then(() => current);

            locks.set(lockKey, queued);

            await previous;

            try {
                return await action();
            } finally {
                release();

                if (locks.get(lockKey) === queued) {
                    locks.delete(lockKey);
                }
            }
        },
    };
}

export type RedisServerSessionStoreOptions = {
    redis: RedisClient;
    namespace: string;
    lockTtlMs?: number;
    lockWaitMs?: number;
    lockRetryMs?: number;
};

const RELEASE_LOCK_SCRIPT = `
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("del", KEYS[1])
end
return 0
`;

const RENEW_LOCK_SCRIPT = `
if redis.call("get", KEYS[1]) == ARGV[1] then
  return redis.call("pexpire", KEYS[1], ARGV[2])
end
return 0
`;

export function createRedisServerSessionStore<T>(
    options: RedisServerSessionStoreOptions,
): ServerSessionStore<T> {
    if (!options.namespace) {
        throw new Error("namespace is required for server-session store.");
    }

    const namespace = options.namespace;

    const redis = options.redis;

    const lockTtlMs = options.lockTtlMs ?? 30_000;

    const lockWaitMs = options.lockWaitMs ?? 20_000;

    const lockRetryMs = options.lockRetryMs ?? 50;

    const sessionKey = (sessionId: string) =>
        `${namespace}:session:${sessionId}`;

    const lockKeyFor = (sessionId: string) => `${namespace}:lock:${sessionId}`;

    return {
        async get(sessionId) {
            const key = sessionKey(sessionId);

            const value = await redis.get(key);

            console.info("[server-session] Redis GET", {
                namespace,
                key,
                hit: value !== undefined,
            });

            if (value === undefined) {
                return undefined;
            }

            return JSON.parse(value) as T;
        },

        async set(sessionId, value, ttlSeconds) {
            const key = sessionKey(sessionId);

            const ttl = Math.max(1, Math.ceil(ttlSeconds));

            await redis.set(key, JSON.stringify(value), {
                EX: ttl,
            });

            console.info("[server-session] Redis SET", {
                namespace,
                key,
                ttlSeconds: ttl,
            });
        },

        async delete(sessionId) {
            const key = sessionKey(sessionId);

            const deleted = await redis.del(key);

            console.info("[server-session] Redis DEL", {
                namespace,
                key,
                deleted: deleted > 0,
            });
        },

        async withLock<R>(
            sessionId: string,
            action: () => Promise<R>,
        ): Promise<R> {
            const key = lockKeyFor(sessionId);

            const lockToken = randomUUID();

            const deadline = Date.now() + lockWaitMs;

            while (Date.now() < deadline) {
                const acquired = await redis.set(key, lockToken, {
                    NX: true,
                    PX: lockTtlMs,
                });

                if (acquired === "OK") {
                    const renewEveryMs = Math.max(
                        1_000,
                        Math.floor(lockTtlMs / 3),
                    );

                    const renewTimer = setInterval(() => {
                        void redis
                            .eval(RENEW_LOCK_SCRIPT, {
                                keys: [key],
                                arguments: [lockToken, String(lockTtlMs)],
                            })
                            .catch((error: unknown) => {
                                console.error(
                                    "[server-session] Redis lock renewal failed",
                                    error,
                                );
                            });
                    }, renewEveryMs);

                    renewTimer.unref?.();

                    try {
                        return await action();
                    } finally {
                        clearInterval(renewTimer);

                        await redis
                            .eval(RELEASE_LOCK_SCRIPT, {
                                keys: [key],
                                arguments: [lockToken],
                            })
                            .catch((error: unknown) => {
                                console.error(
                                    "[server-session] Redis lock release failed",
                                    error,
                                );
                            });
                    }
                }

                await new Promise((resolve) =>
                    setTimeout(resolve, lockRetryMs),
                );
            }

            throw new Error(
                `Timed out waiting for server-session lock for ${sessionId}`,
            );
        },
    };
}

export type EnvironmentServerSessionStoreOptions = {
    redisUrl?: string;
    namespace: string;
    requireRedisInProduction?: boolean;
};

export function createEnvironmentServerSessionStore<T>(
    options: EnvironmentServerSessionStoreOptions,
): ServerSessionStore<T> {
    let resolvedStore: ServerSessionStore<T> | undefined;

    const resolveStore = (): ServerSessionStore<T> => {
        if (resolvedStore) {
            return resolvedStore;
        }

        if (!options.namespace) {
            throw new Error("namespace is required for server-session store.");
        }

        // Resolve lazily so `next build` does not require runtime Kubernetes secrets.
        // The running production process still refuses to use pod-local memory.
        const redisUrl = options.redisUrl ?? process.env.REDIS_URL;

        const namespace = options.namespace;

        if (redisUrl) {
            const redis = createRedisClient({
                url: redisUrl,
                onError: (error) => {
                    console.error("[server-session] Redis client error", {
                        namespace,
                        message:
                            error instanceof Error
                                ? error.message
                                : String(error),
                    });
                },
                onConnect: () => {
                    console.info("[server-session] Redis connected", {
                        namespace,
                    });
                },
            });

            console.info("[server-session] Store selected", {
                type: "redis",
                namespace,
                redisConfigured: true,
            });

            resolvedStore = createRedisServerSessionStore<T>({
                redis,
                namespace,
            });

            return resolvedStore;
        }

        if (
            (options.requireRedisInProduction ?? true) &&
            process.env.NODE_ENV === "production"
        ) {
            throw new Error(
                `REDIS_URL is required in production for stateless BFF sessions (${namespace}).`,
            );
        }

        console.warn("[server-session] Store selected", {
            type: "memory",
            namespace,
            redisConfigured: false,
            nodeEnv: process.env.NODE_ENV,
        });

        resolvedStore = createMemoryServerSessionStore<T>({
            namespace,
        });

        return resolvedStore;
    };

    return {
        get: (sessionId) => resolveStore().get(sessionId),

        set: (sessionId, value, ttlSeconds) =>
            resolveStore().set(sessionId, value, ttlSeconds),

        delete: (sessionId) => resolveStore().delete(sessionId),

        withLock: (sessionId, action) =>
            resolveStore().withLock(sessionId, action),
    };
}
