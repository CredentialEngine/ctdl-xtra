# @credentialengine/auth

Shared Keycloak/NextAuth BFF authentication for the Next.js applications.

## Session model

The package uses NextAuth v4's standard **database** session strategy. The browser receives only NextAuth's opaque `sessionToken` cookie. Users, linked provider accounts, and database-session records are persisted by a NextAuth `Adapter` backed directly by `@credentialengine/redis-client`.

The xTRA configuration supplies `REDIS_URL` and a namespace to `createKeycloakBffAuth`. NextAuth owns the session lifecycle through the Adapter methods `createSession`, `getSessionAndUser`, `updateSession`, and `deleteSession`. OAuth access/refresh/ID tokens are persisted on the standard NextAuth Account record; `BFF_TOKEN_ENCRYPTION=true` encrypts those token fields before they are written to Redis. Logout or session expiry removes all Redis auth state for that login.

OAuth access, refresh, and ID tokens are **not** exposed through the NextAuth session and are intentionally not written into the Adapter account record. They are kept in an encrypted, server-only token vault keyed by the opaque NextAuth database session token. This preserves server-side refresh-token handling without maintaining a second custom authentication session.

BFF code should prefer:

- `getAccessToken(config, request)` for endpoints where authentication is optional.
- `requireAccessToken(config, request)` for endpoints where authentication is mandatory.

Token refresh happens server-side. Refresh operations execute under the backing store's per-session lock, then re-read the token record before using the refresh token. With Redis this protects refresh-token rotation across Kubernetes replicas.

## Redis records

Within the configured namespace, the logical records include:

- `nextauth:user:<id>` — NextAuth user
- `nextauth:account:<provider>:<providerAccountId>` — provider-to-user linkage (OAuth token fields excluded)
- `nextauth:db-session:<sessionToken>` — standard NextAuth database session
- `nextauth:session-metadata:<sessionToken>` — application session metadata such as the active tenant

Database-session and token records expire with the NextAuth session. User/account linkage records do not expire automatically.

## Server-side token encryption

After resolving the backend-only NextAuth secret, the auth package wraps the configured backing store with `createEncryptedServerSessionStore` for OAuth token material. Access, refresh, and ID tokens are serialized and encrypted with AES-256-GCM before Redis sees them. The browser cookie contains only NextAuth's opaque database session token.
