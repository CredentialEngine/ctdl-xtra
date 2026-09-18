# @credentialengine/auth

Shared Keycloak/NextAuth BFF authentication for the Next.js applications.

## Security boundary

OAuth access, refresh, and ID tokens are never placed in the browser-visible NextAuth session and are never stored in the NextAuth JWT cookie. The cookie contains only an opaque `bffSessionId` plus ordinary non-secret identity/session metadata.

Token persistence is supplied by `@credentialengine/server-session`. The auth package does not own an in-process token map.

BFF code should prefer:

- `getAccessToken(config, request)` for endpoints where authentication is optional (Finder).
- `requireAccessToken(config, request)` for endpoints where authentication is mandatory (Accounts/Publisher).

Token refresh happens server-side. Refresh operations execute under the session store's per-session lock, then re-read the token record before using the refresh token. With the Redis store this protects refresh-token rotation across Kubernetes replicas.

## Server-side token encryption

The auth package never persists OAuth token material directly. After resolving the backend-only NextAuth secret, it wraps the configured server-session backing store with `createEncryptedServerSessionStore`. Access, refresh, and ID tokens are serialized and encrypted with AES-256-GCM before Redis or any other backing store sees them. The browser cookie contains only the opaque BFF session identifier and non-secret session metadata.
