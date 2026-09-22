# Telemetry

Server-side OpenTelemetry instrumentation for Credential Engine Next.js apps. Sends telemetry to Azure Monitor / Application Insights.

This package is server-only, it uses the `server-only` package, so the build will fail if it is ever imported from a client component.

## Setup

### 1. Add the dependency

In your app's `package.json`:

```json
{
    "dependencies": {
        "@credentialengine/telemetry": "*"
    }
}
```

### 2. Configure Next.js

In your app's `next.config.ts`, add the package to `transpilePackages`:

```ts
transpilePackages: ["@credentialengine/telemetry"],
```

## Environment variables

| Variable                                             | Required       | Description                                        |
| ---------------------------------------------------- | -------------- | -------------------------------------------------- |
| `NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING` | Yes (deployed) | Application Insights connection string             |
| `NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME`   | Yes            | App name for telemetry (e.g. `accounts`, `finder`) |

## Usage

Create `src/instrumentation.ts` in your app:

```ts
export { register } from "@credentialengine/telemetry";
```

That's it. OpenTelemetry will automatically instrument server-side requests, dependencies, and traces.

## Development

```bash
npm run build --workspace=components/telemetry
```
