# CTDL xTRA

CTDL xTRA is a Next.js App Router application for managing Sources, crawl/discovery runs, benchmark workspaces/runs/strategies, and publishing ETL runs.

## Shared web components

xTRA uses the shared packages under `web/components`:

- `@credentialengine/app-insights` — browser Application Insights integration.
- `@credentialengine/telemetry` — server OpenTelemetry/Azure Monitor instrumentation.
- `@credentialengine/auth` — Keycloak/NextAuth BFF authentication helpers and client auth state.
- `@credentialengine/server-session` — server-side OAuth token/session persistence.
- `@credentialengine/redis-client` — Redis client used by `server-session` in production.

`server-session` uses Redis automatically when `REDIS_URL` is configured. Production refuses to fall back to pod-local memory, so a deployed xTRA instance must provide `REDIS_URL`.

## Authentication model

xTRA follows the same BFF model as Finder:

1. The browser starts Keycloak sign-in through the shared `BffAuthProvider`.
2. NextAuth completes Authorization Code + PKCE on the server.
3. OAuth access, refresh, and ID tokens are stored in the shared server-session store, not in the browser session cookie.
4. The browser receives only the normal NextAuth session cookie containing an opaque server-session identifier.
5. `GET /api/me` returns only browser-safe identity fields.
6. Logout is a CSRF-protected `POST /api/auth/logout` and ends the server-side token session and Keycloak session.

The server-side session lifetime is eight hours. xTRA also refreshes `/api/me` periodically while a user is authenticated so the shared auth package can refresh Keycloak access tokens when needed.

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
BFF_SESSION_ENCRYPTION=true
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
