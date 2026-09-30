# @credentialengine/auth

Shared Keycloak/NextAuth BFF authentication for the Next.js applications.

## Session model

The package uses NextAuth v4's standard **database** session strategy. The browser receives only NextAuth's opaque `sessionToken` cookie. Users, linked provider accounts, and database-session records are persisted by a NextAuth `Adapter` backed directly by `@credentialengine/redis-client`.

The app supplies `REDIS_URL` and a namespace (`BFF_SESSION_NAMESPACE`) to `createKeycloakBffAuth`. NextAuth owns the session lifecycle through the Adapter methods `createSession`, `getSessionAndUser`, `updateSession`, and `deleteSession`.

OAuth access, refresh, and ID tokens are **per login**. Each NextAuth database session has its own token record, keyed by the session token. They are never exposed through the NextAuth session and are not stored on the Account record. So a user signed in on two devices has two independent token sets: logging out, expiring, or refreshing on one device does not affect the other.

Because NextAuth passes the login tokens to the `signIn` callback before it creates the session, the tokens wait briefly in a pending record (60 seconds) that `createSession` then moves onto the new session. If the same user completes two logins at the same instant, one of them may need to sign in again.

BFF code should prefer:

- `getAccessToken(config, request)` for endpoints where authentication is optional.
- `requireAccessToken(config, request)` for endpoints where authentication is mandatory.

Token refresh happens server-side under a per-session Redis lock. The token record is re-read after the lock is taken, so concurrent requests and Kubernetes replicas never use the same refresh token twice.

## Redis records

Within the configured namespace:

Per person:

- `nextauth:user:<id>` — NextAuth user
- `nextauth:user-email:<email>` — email lookup for the user
- `nextauth:account:<provider>:<providerAccountId>` — link from the provider identity to the user (no tokens)
- `nextauth:user-accounts:<userId>` — the user's linked accounts

Per login:

- `nextauth:session:<sessionToken>` — standard NextAuth database session
- `nextauth:session-tokens:<sessionToken>` — this login's OAuth tokens
- `nextauth:session-metadata:<sessionToken>` — application session metadata such as the active tenant

Short-lived:

- `nextauth:pending-tokens:<provider>:<providerAccountId>` — tokens waiting for `createSession` during login
- `nextauth:lock:refresh:<sessionToken>` — refresh lock

Per-login records expire with their session. Per-person records expire with the user's longest-lived session. Logout and session expiry remove only that login's records.

## Token encryption

Token records are encrypted with AES-256-GCM using a key derived from the NextAuth secret. Encryption is on by default. Set `BFF_TOKEN_ENCRYPTION=false` (or pass `encryptTokens: false`) to store them in plain JSON, for local debugging only. Records written in either mode stay readable after switching.

## Upgrading from tokens on the Account record

Existing sessions have no token record, so their users are asked to sign in once more after deploying. Token fields left on old Account records are removed on each user's next login.
