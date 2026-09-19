# @credentialengine/server-session

Shared server-only session persistence for stateless BFF deployments.

- Redis-backed sessions with TTL for Kubernetes/multi-replica deployments.
- Distributed per-session locking for safe OAuth refresh-token rotation.
- Process-local memory implementation for local development only.
- `createEnvironmentServerSessionStore()` uses `REDIS_URL` when present and rejects production startup without Redis by default.

The browser never interacts with this package. It stores values keyed by opaque server session IDs.

## Encryption at rest

OAuth token records must be wrapped with `createEncryptedServerSessionStore` before they are used as BFF token storage. The auth package does this automatically using the resolved backend-only NextAuth secret and an application/client-specific purpose string.

Redis therefore stores an AES-256-GCM envelope (`v`, `iv`, `tag`, `ciphertext`) rather than plaintext access, refresh, or ID tokens. The encryption key is derived only inside the server process; it is never written to Redis or returned to browser code.

Changing the NextAuth secret intentionally makes existing Redis session records unreadable. Users must authenticate again after such a rotation unless a future key-rotation/multi-key migration strategy is configured.
