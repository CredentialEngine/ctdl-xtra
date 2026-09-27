import { jest } from "@jest/globals";

const store = new Map();
const hashStore = new Map();

const redisClient = {
    isReady: false,
    on: jest.fn(),
    connect: jest.fn(async function () {
        this.isReady = true;
    }),
    quit: jest.fn(async function () {
        this.isReady = false;
    }),
    get: jest.fn(async (key) => store.get(key) ?? null),
    set: jest.fn(async (key, value, options = {}) => {
        if (options.NX && store.has(key)) {
            return null;
        }
        if (options.XX && !store.has(key)) {
            return null;
        }
        store.set(key, value);
        return "OK";
    }),
    del: jest.fn(async (keys) => {
        let count = 0;
        for (const key of keys) {
            if (store.delete(key)) {
                count++;
            }
        }
        return count;
    }),
    exists: jest.fn(async (keys) => {
        let count = 0;
        for (const key of keys) {
            if (store.has(key)) {
                count++;
            }
        }
        return count;
    }),
    expire: jest.fn(async () => 1),
    ttl: jest.fn(async () => -1),
    incr: jest.fn(async (key) => {
        const current = parseInt(store.get(key) ?? "0", 10);
        const next = current + 1;
        store.set(key, String(next));
        return next;
    }),
    incrBy: jest.fn(async (key, increment) => {
        const current = parseInt(store.get(key) ?? "0", 10);
        const next = current + increment;
        store.set(key, String(next));
        return next;
    }),
    hGet: jest.fn(async (key, field) => {
        const hash = hashStore.get(key);
        if (!hash) {
            return null;
        }
        return hash.get(field) ?? null;
    }),
    hSet: jest.fn(async (key, field, value) => {
        if (!hashStore.has(key)) {
            hashStore.set(key, new Map());
        }
        const hash = hashStore.get(key);
        const isNew = !hash.has(field);
        hash.set(field, value);
        return isNew ? 1 : 0;
    }),
    hGetAll: jest.fn(async (key) => {
        const hash = hashStore.get(key);
        if (!hash) {
            return {};
        }
        return Object.fromEntries(hash);
    }),
    hDel: jest.fn(async (key, fields) => {
        const hash = hashStore.get(key);
        if (!hash) {
            return 0;
        }
        let count = 0;
        for (const field of fields) {
            if (hash.delete(field)) {
                count++;
            }
        }
        return count;
    }),
    eval: jest.fn(async () => 0),
};

jest.unstable_mockModule("redis", () => ({
    createClient: jest.fn(() => redisClient),
}));

const { createRedisClient } = await import("../dist/index.js");

beforeEach(() => {
    store.clear();
    hashStore.clear();
    redisClient.isReady = false;
    jest.clearAllMocks();
});

describe("connection lifecycle", () => {
    test("starts not ready, becomes ready after connect", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        expect(redis.isReady).toBe(false);

        await redis.connect();

        expect(redis.isReady).toBe(true);
    });

    test("disconnect resets readiness", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.connect();

        await redis.disconnect();

        expect(redis.isReady).toBe(false);
        expect(redisClient.quit).toHaveBeenCalled();
    });

    test("fires onConnect and onError callbacks", async () => {
        const onConnect = jest.fn();
        const onError = jest.fn();

        const redis = createRedisClient({
            url: "redis://localhost:6379",
            onConnect,
            onError,
        });

        await redis.connect();

        expect(onConnect).toHaveBeenCalledTimes(1);
    });

    test("raw() exposes the underlying client", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        const raw = await redis.raw();

        expect(raw).toBe(redisClient);
    });
});

describe("string operations", () => {
    test("get returns undefined for missing keys", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        const result = await redis.get("missing");

        expect(result).toBeUndefined();
    });

    test("set and get round-trip a value", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        await redis.set("key1", "value1");

        expect(await redis.get("key1")).toBe("value1");
    });

    test("set passes EX option to redis", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        await redis.set("ttl-key", "data", { EX: 30 });

        expect(redisClient.set).toHaveBeenCalledWith(
            "ttl-key",
            "data",
            expect.objectContaining({ EX: 30 }),
        );
    });

    test("set passes PX option to redis", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        await redis.set("px-key", "data", { PX: 5000 });

        expect(redisClient.set).toHaveBeenCalledWith(
            "px-key",
            "data",
            expect.objectContaining({ PX: 5000 }),
        );
    });

    test("set with NX fails when key exists", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.set("locked", "first");

        const result = await redis.set("locked", "second", { NX: true });

        expect(result).toBeUndefined();
        expect(await redis.get("locked")).toBe("first");
    });

    test("set with NX succeeds when key is absent", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        const result = await redis.set("new-key", "value", { NX: true });

        expect(result).toBe("OK");
        expect(await redis.get("new-key")).toBe("value");
    });

    test("set with XX fails when key is absent", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        const result = await redis.set("ghost", "value", { XX: true });

        expect(result).toBeUndefined();
    });

    test("set with XX succeeds when key exists", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.set("exists", "old");

        const result = await redis.set("exists", "new", { XX: true });

        expect(result).toBe("OK");
        expect(await redis.get("exists")).toBe("new");
    });

    test("del removes keys and returns count", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.set("a", "1");
        await redis.set("b", "2");

        const deleted = await redis.del("a", "b", "c");

        expect(deleted).toBe(2);
        expect(await redis.get("a")).toBeUndefined();
        expect(await redis.get("b")).toBeUndefined();
    });
});

describe("key lifecycle", () => {
    test("exists returns count of existing keys", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.set("real", "yes");

        expect(await redis.exists("real")).toBe(1);
        expect(await redis.exists("fake")).toBe(0);
        expect(await redis.exists("real", "fake")).toBe(1);
    });

    test("expire delegates to redis", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.set("exp-key", "data");

        const result = await redis.expire("exp-key", 120);

        expect(result).toBe(true);
        expect(redisClient.expire).toHaveBeenCalledWith("exp-key", 120);
    });

    test("ttl delegates to redis", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        const result = await redis.ttl("any-key");

        expect(result).toBe(-1);
        expect(redisClient.ttl).toHaveBeenCalledWith("any-key");
    });
});

describe("counters", () => {
    test("incr increments from zero", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        expect(await redis.incr("counter")).toBe(1);
        expect(await redis.incr("counter")).toBe(2);
        expect(await redis.incr("counter")).toBe(3);
    });

    test("incrBy adds the specified amount", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        expect(await redis.incrBy("big", 10)).toBe(10);
        expect(await redis.incrBy("big", 5)).toBe(15);
    });

    test("incrBy with negative value decrements", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.incrBy("val", 20);

        expect(await redis.incrBy("val", -7)).toBe(13);
    });
});

describe("hash operations", () => {
    test("hGet returns undefined for missing hash or field", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        expect(await redis.hGet("no-hash", "field")).toBeUndefined();
    });

    test("hSet and hGet round-trip a field", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        await redis.hSet("user:1", "name", "Alice");
        await redis.hSet("user:1", "email", "alice@example.com");

        expect(await redis.hGet("user:1", "name")).toBe("Alice");
        expect(await redis.hGet("user:1", "email")).toBe("alice@example.com");
    });

    test("hGetAll returns all fields", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.hSet("user:2", "name", "Bob");
        await redis.hSet("user:2", "role", "admin");

        const all = await redis.hGetAll("user:2");

        expect(all).toEqual({
            name: "Bob",
            role: "admin",
        });
    });

    test("hGetAll returns empty object for missing hash", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });

        expect(await redis.hGetAll("empty")).toEqual({});
    });

    test("hDel removes fields and returns count", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        await redis.hSet("user:3", "name", "Carol");
        await redis.hSet("user:3", "email", "carol@example.com");

        const deleted = await redis.hDel("user:3", "email", "missing");

        expect(deleted).toBe(1);
        expect(await redis.hGet("user:3", "email")).toBeUndefined();
        expect(await redis.hGet("user:3", "name")).toBe("Carol");
    });
});

describe("eval", () => {
    test("passes script, keys, and arguments to redis", async () => {
        const redis = createRedisClient({ url: "redis://localhost:6379" });
        const script = 'return redis.call("get", KEYS[1])';

        await redis.eval(script, {
            keys: ["mykey"],
            arguments: ["arg1"],
        });

        expect(redisClient.eval).toHaveBeenCalledWith(script, {
            keys: ["mykey"],
            arguments: ["arg1"],
        });
    });
});
