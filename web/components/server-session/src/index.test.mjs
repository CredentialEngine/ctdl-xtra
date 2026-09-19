import { jest } from "@jest/globals";

const redisValues = new Map();

// A fake RedisClient that matches the interface createRedisServerSessionStore expects.
function createFakeRedisClient() {
    return {
        isReady: true,
        get: jest.fn(async (key) => {
            const value = redisValues.get(key);
            if (value === undefined) {
                return undefined;
            }
            return value;
        }),
        set: jest.fn(async (key, value, options = {}) => {
            if (options.NX && redisValues.has(key)) {
                return undefined;
            }
            redisValues.set(key, value);
            return "OK";
        }),
        del: jest.fn(async (...keys) => {
            let count = 0;
            for (const key of keys) {
                if (redisValues.delete(key)) {
                    count++;
                }
            }
            return count;
        }),
        eval: jest.fn(async (script, { keys, arguments: args }) => {
            const [key] = keys;
            if (script.includes('redis.call("del"')) {
                if (redisValues.get(key) === args[0]) {
                    redisValues.delete(key);
                    return 1;
                }
                return 0;
            }
            return redisValues.get(key) === args[0] ? 1 : 0;
        }),
    };
}

// Mock @credentialengine/redis-client so createEnvironmentServerSessionStore
// can call createRedisClient and get a fake back.
const fakeRedisClientForEnv = createFakeRedisClient();

jest.unstable_mockModule("@credentialengine/redis-client", () => ({
    createRedisClient: jest.fn(() => fakeRedisClientForEnv),
    RedisClient: class {},
}));

const {
    createEncryptedServerSessionStore,
    createEnvironmentServerSessionStore,
    createJsonServerSessionStore,
    createMemoryServerSessionStore,
    createRedisServerSessionStore,
} = await import("../dist/index.js");

function rawMemoryStore() {
    const values = new Map();
    return {
        values,
        async get(id) {
            return values.get(id);
        },
        async set(id, value) {
            values.set(id, value);
        },
        async delete(id) {
            values.delete(id);
        },
        async withLock(_id, action) {
            return action();
        },
    };
}

describe("encrypted server-session store", () => {
    test("round-trips values without persisting token plaintext", async () => {
        const backing = rawMemoryStore();
        const store = createEncryptedServerSessionStore(backing, {
            secret: "test-secret",
            purpose: "oauth",
        });
        const value = {
            accessToken: "very-secret-token",
            refreshToken: "refresh-secret",
        };

        await store.set("session-1", value, 60);

        const persisted = backing.values.get("session-1");
        expect(typeof persisted).toBe("string");
        expect(persisted).not.toContain("very-secret-token");
        expect(persisted).not.toContain("refresh-secret");
        expect(await store.get("session-1")).toEqual(value);
    });

    test("fails closed for the wrong key or tampered ciphertext", async () => {
        const backing = rawMemoryStore();
        const first = createEncryptedServerSessionStore(backing, {
            secret: "one",
        });
        await first.set("session-2", { value: 42 }, 60);

        const wrongKey = createEncryptedServerSessionStore(backing, {
            secret: "two",
        });
        await expect(wrongKey.get("session-2")).rejects.toThrow(
            "Unable to decrypt",
        );

        const envelope = JSON.parse(backing.values.get("session-2"));
        envelope.tag = Buffer.alloc(8).toString("base64url");
        backing.values.set("session-2", JSON.stringify(envelope));
        await expect(first.get("session-2")).rejects.toThrow(
            "Unable to decrypt",
        );
    });
});

describe("JSON and memory stores", () => {
    test("JSON wrapper serializes and deserializes values", async () => {
        const backing = rawMemoryStore();
        const store = createJsonServerSessionStore(backing);
        await store.set("plain", { ok: true }, 10);
        expect(backing.values.get("plain")).toBe('{"ok":true}');
        expect(await store.get("plain")).toEqual({ ok: true });
    });

    test("memory store expires, deletes, and namespaces values", async () => {
        jest.useFakeTimers();
        jest.setSystemTime(new Date("2026-01-01T00:00:00Z"));
        const a = createMemoryServerSessionStore({ namespace: "a-test" });
        const b = createMemoryServerSessionStore({ namespace: "b-test" });
        await a.set("id", { x: 1 }, 1);
        expect(await a.get("id")).toEqual({ x: 1 });
        expect(await b.get("id")).toBeUndefined();
        jest.advanceTimersByTime(1001);
        expect(await a.get("id")).toBeUndefined();
        await a.set("id", { x: 2 }, 10);
        await a.delete("id");
        expect(await a.get("id")).toBeUndefined();
        jest.useRealTimers();
    });

    test("memory lock serializes work for the same session", async () => {
        const store = createMemoryServerSessionStore({
            namespace: "lock-test",
        });
        const order = [];
        let release;
        const gate = new Promise((resolve) => {
            release = resolve;
        });
        const first = store.withLock("same", async () => {
            order.push("first-start");
            await gate;
            order.push("first-end");
        });
        const second = store.withLock("same", async () => order.push("second"));
        await Promise.resolve();
        expect(order).toEqual(["first-start"]);
        release();
        await Promise.all([first, second]);
        expect(order).toEqual(["first-start", "first-end", "second"]);
    });
});

describe("Redis store", () => {
    let fakeRedis;

    beforeEach(() => {
        redisValues.clear();
        fakeRedis = createFakeRedisClient();
    });

    test("persists sessions with TTL and removes them", async () => {
        const store = createRedisServerSessionStore({
            redis: fakeRedis,
            namespace: "unit",
        });

        await store.set("abc", { value: 1 }, 12.2);

        expect(fakeRedis.set).toHaveBeenCalledWith(
            "unit:session:abc",
            '{"value":1}',
            { EX: 13 },
        );
        expect(await store.get("abc")).toEqual({ value: 1 });

        await store.delete("abc");

        expect(await store.get("abc")).toBeUndefined();
    });

    test("uses an owned distributed lock and releases it", async () => {
        const store = createRedisServerSessionStore({
            redis: fakeRedis,
            namespace: "unit-lock",
        });

        const result = await store.withLock("abc", async () => "done");

        expect(result).toBe("done");
        expect(fakeRedis.set).toHaveBeenCalledWith(
            "unit-lock:lock:abc",
            expect.any(String),
            expect.objectContaining({ NX: true, PX: 30000 }),
        );
        expect(fakeRedis.eval).toHaveBeenCalled();
        expect(redisValues.has("unit-lock:lock:abc")).toBe(false);
    });

    test("throws when namespace is missing", () => {
        expect(() =>
            createRedisServerSessionStore({
                redis: fakeRedis,
                namespace: "",
            }),
        ).toThrow("namespace is required");
    });
});

describe("environment store selection", () => {
    const originalEnv = process.env;

    afterEach(() => {
        process.env = { ...originalEnv };
    });

    test("selects Redis when REDIS_URL is configured", async () => {
        process.env = {
            ...originalEnv,
            NODE_ENV: "development",
            REDIS_URL: "redis://localhost:6379",
        };

        const store = createEnvironmentServerSessionStore({
            namespace: "env-redis",
        });

        await store.set("x", "value", 10);

        expect(fakeRedisClientForEnv.set).toHaveBeenCalledWith(
            "env-redis:session:x",
            '"value"',
            {
                EX: 10,
            },
        );
    });

    test("uses memory in development without Redis", async () => {
        process.env = { ...originalEnv, NODE_ENV: "development" };
        delete process.env.REDIS_URL;

        const store = createEnvironmentServerSessionStore({
            namespace: "env-memory",
        });

        await store.set("x", "value", 10);

        expect(await store.get("x")).toBe("value");
    });

    test("fails in production when Redis is required but missing", async () => {
        process.env = { ...originalEnv, NODE_ENV: "production" };
        delete process.env.REDIS_URL;

        const store = createEnvironmentServerSessionStore({
            namespace: "env-production",
        });

        expect(() => store.get("x")).toThrow(
            "REDIS_URL is required in production",
        );
    });
});
