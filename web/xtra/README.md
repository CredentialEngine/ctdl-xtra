# CTDL xTRA

CTDL xTRA is a Next.js App Router application for managing Sources, crawl/discovery runs, benchmark workspaces/runs/strategies, and publishing ETL runs.

## Shared web components

xTRA uses the shared packages under `web/components`:

- `@credentialengine/app-insights` — browser Application Insights integration.
- `@credentialengine/telemetry` — server OpenTelemetry/Azure Monitor instrumentation.
- `@credentialengine/auth` — Keycloak/NextAuth BFF authentication helpers and client auth state.
- `@credentialengine/auth` — NextAuth database-session configuration and Redis adapter.
- `@credentialengine/redis-client` — Redis connection used directly by the auth adapter.

NextAuth database sessions require `REDIS_URL`. User, Account, Session, and related indexes are persisted directly through the Redis-backed NextAuth adapter.

## Authentication model

xTRA follows the same BFF model as Finder:

1. The browser starts Keycloak sign-in through the shared `BffAuthProvider`.
2. NextAuth completes Authorization Code + PKCE on the server.
3. NextAuth uses its standard `database` session strategy with a Redis-backed Adapter.
4. The browser receives only the normal NextAuth session cookie containing an opaque database `sessionToken`; users, provider links, and sessions live in Redis.
5. OAuth access, refresh, and ID tokens stay server-only in the session-scoped Keycloak Account record. Logout or session expiry removes the session, user, account, and related indexes from Redis.
6. `GET /api/me` returns only browser-safe identity fields.
7. Every SPA request to an xTRA BFF endpoint carries the xTRA double-submit CSRF token, including read-only `GET` requests.
8. Logout is a CSRF-protected `POST /api/auth/logout`; it deletes the NextAuth database session and the session-scoped Keycloak Account/token record, while preserving the token-free identity link needed for the next login, then performs best-effort Keycloak logout.

The SPA obtains its xTRA CSRF token from `GET /api/csrf`, then uses the shared `bffFetch` helper for BFF calls. `/api/csrf` is necessarily exempt because it bootstraps the token. Framework authentication endpoints under `/api/auth/*` keep NextAuth's own CSRF/redirect behavior, and `/api/up` remains an unauthenticated health check.

The NextAuth database-session lifetime is eight hours, with session-expiry writes throttled to once per hour. xTRA also refreshes `/api/me` periodically while a user is authenticated so the shared auth package can refresh Keycloak access tokens when needed.

## Telemetry

Browser telemetry is initialized from `@credentialengine/app-insights` using runtime config returned by `/api/config`.

Server telemetry is registered by `instrumentation.ts` through `@credentialengine/telemetry`. Local development can disable server telemetry with:

```env
NEXT_PUBLIC_NODE_ENV=development
```

Deployed environments should provide:

```env
APPLICATIONINSIGHTS_CONNECTION_STRING=...
APPLICATION_INSIGHTS_CLOUD_ROLE_NAME=xtra
```

## Environment

Copy `.env.example` to a local environment file and configure the values you need.

Important authentication/session values:

```env
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=replace-with-a-strong-random-value
OIDC_AUTHORITY=http://localhost:8080/realms/CE-Dev
OIDC_CLIENT_ID=Xtra
REDIS_URL=redis://localhost:6379
BFF_SESSION_NAMESPACE=credentialengine:xtra
BFF_TOKEN_ENCRYPTION=true
```

When xTRA runs in Docker and Redis/Keycloak/workflow services run on the Windows/macOS host, use `host.docker.internal` for server-to-host URLs. Keep browser-facing `NEXTAUTH_URL`/`APP_URL` on `localhost:3000`.

## Development

Run commands from `web` so npm workspaces can resolve and build the shared packages:

```bash
npm install
npm run dev:xtra
```

Useful commands:

```bash
npm run build:components
npm run build:xtra
npm run typecheck:xtra
npm run lint
npm run test:components
npm run prettier
```

The xTRA workspace also has its own `dev`, `build`, `lint`, `typecheck`, `prettier`, and `check` commands. Its `predev` and `prebuild` hooks build the shared component packages first.

## Docker

Build from the `web` directory because the Docker build context includes both xTRA and the shared component workspaces:

```bash
docker build -t xtra:test -f xtra/Dockerfile .
```

Run the image with a local environment file:

```bash
docker run --rm -p 3000:3000 --env-file xtra/.env.development xtra:test
```

The production image uses Next.js standalone output and runs as a non-root user.

## Long-running workflows

Crawling, discovery, ETL, benchmark execution, and publishing orchestration are external workflow concerns. xTRA's BFF will call the configured workflow API as those integrations are implemented.
