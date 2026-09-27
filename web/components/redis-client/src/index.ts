import { createClient, type RedisClientType } from "redis";

export type RedisClientOptions = {
    url: string;
    connectTimeoutMs?: number;
    onError?: (error: unknown) => void;
    onConnect?: () => void;
};

export type RedisSetOptions = {
    /** Expire after this many seconds. */
    EX?: number;
    /** Expire after this many milliseconds. */
    PX?: number;
    /** Only set if the key does NOT exist. */
    NX?: boolean;
    /** Only set if the key DOES exist. */
    XX?: boolean;
};

export type RedisEvalOptions = {
    keys: string[];
    arguments: string[];
};

export class RedisClient {
    private readonly options: RedisClientOptions;
    private client: RedisClientType | undefined;
    private connectPromise: Promise<RedisClientType> | undefined;

    constructor(options: RedisClientOptions) {
        this.options = options;
    }

    get isReady(): boolean {
        if (this.client) {
            return this.client.isReady;
        }
        return false;
    }

    async connect(): Promise<void> {
        await this.getClient();
    }

    async disconnect(): Promise<void> {
        if (this.client?.isReady) {
            await this.client.quit();
        }
        this.client = undefined;
        this.connectPromise = undefined;
    }

    async raw(): Promise<RedisClientType> {
        return this.getClient();
    }

    async get(key: string): Promise<string | undefined> {
        const redis = await this.getClient();
        const value = await redis.get(key);
        if (value === null) {
            return undefined;
        }
        return value;
    }

    async set(
        key: string,
        value: string,
        options?: RedisSetOptions,
    ): Promise<string | undefined> {
        const redis = await this.getClient();
        const redisOpts: Record<string, unknown> = {};
        if (options?.EX !== undefined) {
            redisOpts.EX = options.EX;
        }
        if (options?.PX !== undefined) {
            redisOpts.PX = options.PX;
        }
        if (options?.NX) {
            redisOpts.NX = true;
        }
        if (options?.XX) {
            redisOpts.XX = true;
        }
        const result = await redis.set(key, value, redisOpts);
        if (result === null) {
            return undefined;
        }
        return result;
    }

    async del(...keys: string[]): Promise<number> {
        const redis = await this.getClient();
        return redis.del(keys);
    }

    async exists(...keys: string[]): Promise<number> {
        const redis = await this.getClient();
        return redis.exists(keys);
    }

    async expire(key: string, seconds: number): Promise<boolean> {
        const redis = await this.getClient();
        return (await redis.expire(key, seconds)) === 1;
    }

    async ttl(key: string): Promise<number> {
        const redis = await this.getClient();
        return redis.ttl(key);
    }

    async incr(key: string): Promise<number> {
        const redis = await this.getClient();
        return redis.incr(key);
    }

    async incrBy(key: string, increment: number): Promise<number> {
        const redis = await this.getClient();
        return redis.incrBy(key, increment);
    }

    async hGet(key: string, field: string): Promise<string | undefined> {
        const redis = await this.getClient();
        return (await redis.hGet(key, field)) ?? undefined;
    }

    async hSet(key: string, field: string, value: string): Promise<number> {
        const redis = await this.getClient();
        return redis.hSet(key, field, value);
    }

    async hGetAll(key: string): Promise<Record<string, string>> {
        const redis = await this.getClient();
        return redis.hGetAll(key);
    }

    async hDel(key: string, ...fields: string[]): Promise<number> {
        const redis = await this.getClient();
        return redis.hDel(key, fields);
    }

    async eval(script: string, options: RedisEvalOptions): Promise<unknown> {
        const redis = await this.getClient();
        return redis.eval(script, {
            keys: options.keys,
            arguments: options.arguments,
        });
    }

    private async getClient(): Promise<RedisClientType> {
        if (this.client?.isReady) {
            return this.client;
        }
        if (this.connectPromise) {
            return this.connectPromise;
        }

        const onError =
            this.options.onError ??
            ((err: unknown) => {
                console.error("[redis-client] error", {
                    message: err instanceof Error ? err.message : String(err),
                });
            });

        const onConnect =
            this.options.onConnect ??
            (() => {
                console.info("[redis-client] connected");
            });

        const candidate = createClient({
            url: this.options.url,
            socket: {
                connectTimeout: this.options.connectTimeoutMs ?? 5_000,
            },
        });

        candidate.on("error", onError);

        this.connectPromise = candidate
            .connect()
            .then(() => {
                this.client = candidate as RedisClientType;
                onConnect();
                return this.client;
            })
            .catch((error) => {
                onError(error);
                throw error;
            })
            .finally(() => {
                this.connectPromise = undefined;
            });

        return this.connectPromise;
    }
}

export function createRedisClient(options: RedisClientOptions): RedisClient {
    return new RedisClient(options);
}
