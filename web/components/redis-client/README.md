# @credentialengine/redis-client

Shared server-only Redis client for Credential Engine Node.js applications and libraries.

- Lazily creates and connects a Redis client.
- Reuses a single connection per `RedisClient` instance.
- Protects concurrent startup with a shared connection promise.
- Supports common Redis string, key, hash, list, set, sorted-set, counter, pub/sub, and scripting operations.
- Exposes the underlying `redis` client through `raw()` when an operation is not covered by the wrapper.
- Supports configurable connection timeout and connection/error callbacks.

## Usage

```ts
import { createRedisClient } from "@credentialengine/redis-client";

const redis = createRedisClient({
    url: process.env.REDIS_URL!,
});

await redis.set("example:key", "value", { EX: 300 });

const value = await redis.get("example:key");
```

The client connects lazily on the first Redis operation.

Call `connect()` when an application wants to establish the connection explicitly during startup, and `disconnect()` during application shutdown when appropriate.

## Package dependency

Server-side libraries such as `@credentialengine/auth` should depend on this package instead of importing or creating a Redis client directly.

```json
{
    "dependencies": {
        "@credentialengine/redis-client": "*"
    }
}
```

Then import the shared client where needed:

```ts
import {
    createRedisClient,
    type RedisClient,
} from "@credentialengine/redis-client";
```

For example, `@credentialengine/auth` uses this package for Redis connection management while keeping NextAuth persistence, token-field encryption, TTL handling, and refresh locking in the auth layer.

## Testing

Run the Redis client tests from the repository root:

```bash
npm test --workspace=@credentialengine/redis-client
```

The test script builds the package before running the `redis-client` Jest project.

Tests that connect to Redis use `REDIS_URL` when provided and otherwise default to:

```text
redis://localhost:6379
```

A local Redis instance must be running for integration tests that perform actual Redis operations.
