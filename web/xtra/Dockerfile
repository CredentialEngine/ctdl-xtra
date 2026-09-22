# ---- Build Stage ----
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0-1758699349 AS builder

WORKDIR /app
USER root

# Install Node.js 26
RUN microdnf install -y curl tar gzip libstdc++ \
    && curl -fsSL https://rpm.nodesource.com/setup_26.x | bash - \
    && microdnf install -y nodejs \
    && microdnf clean all

RUN node --version && npm --version

# Copy workspace manifests first so npm ci can resolve every local workspace
# and dependency installation can be cached independently of source changes.
COPY package.json package-lock.json ./
COPY components/appInsights/package.json ./components/appInsights/
COPY components/auth/package.json ./components/auth/
COPY components/redis-client/package.json ./components/redis-client/
COPY components/telemetry/package.json ./components/telemetry/
COPY xtra/package.json ./xtra/

# Install build and runtime dependencies. Dev dependencies are required in the
# builder for TypeScript, Next.js, PostCSS, Tailwind, and shared package builds.
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc,required=false \
    npm install --ignore-scripts=false --no-fund

# Fail the image build for high or critical dependency vulnerabilities.
RUN --mount=type=secret,id=npmrc,target=/root/.npmrc,required=false \
    npm audit --audit-level=high

# Copy all shared components used directly or transitively by xTRA.
COPY components/appInsights ./components/appInsights
COPY components/auth ./components/auth
COPY components/redis-client ./components/redis-client
COPY components/telemetry ./components/telemetry

# Copy xTRA source and configuration.
COPY xtra ./xtra

# Build shared packages in dependency order, then build xTRA standalone output.
RUN npm run build:xtra

# ---- Runtime Stage ----
FROM registry.access.redhat.com/ubi10/ubi-micro:10.0-1754556444 AS runtime

WORKDIR /app

# Copy Node.js runtime from the builder image.
COPY --from=builder /usr/bin/node /usr/bin/node
COPY --from=builder /usr/lib64/ /usr/lib64/

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Next.js standalone output contains the production dependency closure,
# including the shared auth/session/redis packages required at runtime.
COPY --from=builder /app/xtra/public ./xtra/public
COPY --from=builder /app/xtra/.next/standalone ./
COPY --from=builder /app/xtra/.next/static ./xtra/.next/static

# Run as a non-root user.
RUN echo "appuser:x:1001:0:appuser:/home/appuser:/sbin/nologin" >> /etc/passwd \
    && chown -R 1001:0 /app

USER 1001
EXPOSE 3000

CMD ["node", "xtra/server.js"]
