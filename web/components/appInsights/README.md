# AppInsights

Client-side Application Insights for Credential Engine Next.js apps. Tracks page views, API calls, and click events in the browser.

For server-side telemetry (OpenTelemetry / Azure Monitor), see the separate [`@credentialengine/telemetry`](../telemetry/README.md) package.

## Setup

This package is consumed via npm workspaces from the `web` monorepo root.

### 1. Register your app in workspaces

In `web/package.json`, add your app to the `workspaces` array:

```json
{
    "workspaces": [
        "your-app", // add your project folder name
        "components/*"
    ]
}
```

### 2. Add the dependency

In your app's `package.json`:

```json
{
    "dependencies": {
        "@credentialengine/app-insights": "*"
    }
}
```

Then run `npm install` from the `web` root.

### 3. Configure Next.js

In your app's `next.config.ts`, add the package to `transpilePackages`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
    transpilePackages: ["@credentialengine/app-insights"],
};

export default nextConfig;
```

### 3. Peer dependencies

Your app must have these installed:

- `next` ^16.2.9
- `react` 19.2.3

## Environment variables

| Variable                                             | Required       | Description                                       |
| ---------------------------------------------------- | -------------- | ------------------------------------------------- |
| `NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING` | Yes (deployed) | Application Insights connection string            |
| `NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME`   | Yes            | App name (e.g. `accounts`, `publisher`, `finder`) |

## Usage

### Page view tracking

The `Analytics` component tracks page views on route changes. Add it to your layout:

```tsx
//layout
"use client";

import { Suspense } from "react";
import { Analytics } from "@credentialengine/app-insights";
import {
    ConfigContextProvider,
    useConfigContext,
} from "./components/providers/configProvider";

function AnalyticsWithConfig() {
    const { NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING } =
        useConfigContext();

    return (
        <Analytics
            connectionString={
                NEXT_PUBLIC_APPLICATION_INSIGHTS_CONNECTION_STRING
            }
            roleName={
                process.env.NEXT_PUBLIC_APPLICATION_INSIGHTS_CLOUD_ROLE_NAME!
            }
        />
    );
}

export default function Providers({ children }: { children: React.ReactNode }) {
    return (
        <ConfigContextProvider>
            <Suspense fallback={null}>
                <AnalyticsWithConfig />
            </Suspense>
            {children}
        </ConfigContextProvider>
    );
}
```

## Exports

| Export                  | Description                                                   |
| ----------------------- | ------------------------------------------------------------- |
| `Analytics`             | React component for page view tracking                        |
| `initializeAppInsights` | Manual initialization of the Application Insights browser SDK |

## Development

```bash
npm run build --workspace=components/appInsights
```

If the build has stale files, clean first:

```powershell
Remove-Item -Recurse -Force components\appInsights\dist
npm run build --workspace=components/appInsights
```

The consuming app picks up the new `dist/` on the next dev server restart. No reinstall is needed with workspaces.
