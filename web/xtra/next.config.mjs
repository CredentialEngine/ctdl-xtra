import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(appRoot, "..");

/** @type {import('next').NextConfig} */
const nextConfig = {
    output: "standalone",

    // npm installs workspace dependencies at web/node_modules.  Keep file tracing
    // rooted at the npm workspace so standalone output can include hoisted deps.
    outputFileTracingRoot: workspaceRoot,

    turbopack: {
        // xTRA lives at web/xtra, while Next.js and the shared CE components are
        // hoisted/resolved from the parent npm workspace (web).  Turbopack must be
        // allowed to see that parent directory.
        root: workspaceRoot,
    },

    transpilePackages: [
        "@credentialengine/app-insights",
        "@credentialengine/telemetry",
        "@credentialengine/auth",
        "@credentialengine/server-session",
    ],
};

export default nextConfig;
