# Infrastructure Summary

Quick reference for app developers — endpoints, names, and how to find/change things in each environment.

> **Current state:** the only live environment is `PRODUCTION`. The previous `staging` env was decommissioned and will be replaced by a `SANDBOX` env (per the xTRA Design Document). Until SANDBOX is built, the release / promote workflows are disabled.

## Environments

| | Production |
|---|---|
| **App URL** | `https://xtra.credentialengineregistry.org` |
| **EKS cluster** | `ctdl-xtra-prod` |
| **K8s namespace** | `ctdl-xtra` |
| **AWS region** | `us-east-1` |
| **AWS account** | `996810415034` |

## Container images (ECR)

| | Production |
|---|---|
| API repo | `ctdl-xtra/api` |
| Worker repo | `ctdl-xtra/worker` |
| Base image | TBD — was `ctdl-xtra-staging/base`; will move to a env-neutral repo when SANDBOX is built |
| Image tag pattern | `sha-<7char>` only |

All images are at `996810415034.dkr.ecr.us-east-1.amazonaws.com/<repo>:<tag>`.

## Database (RDS PostgreSQL)

| | Production |
|---|---|
| Endpoint | `ctdl-xtra-prod-postgres.cwdkv5tua6nq.us-east-1.rds.amazonaws.com:5432` |
| DB name | `ctdl_xtra` |
| Engine | PostgreSQL 17.5 |
| HA | Multi-AZ |
| Reachable from | inside cluster only (private subnets) |

`DATABASE_URL` (full connection string with credentials) is injected as an env var via the app secret — never hardcoded.

## Cache / Queue (Redis)

Runs **inside the cluster** as a StatefulSet (not AWS ElastiCache).

- Service DNS: `redis.ctdl-xtra.svc.cluster.local:6379`
- Auth: password-only (no TLS); injected via env var
- Persistence: AOF + RDB on EBS-backed PVC
- Used by BullMQ workers for job queues

`REDIS_URL` is injected as an env var by the app secret.

## Shared file storage (EFS)

- Mount path in pod: `/data/extractions`
- ReadWriteMany — both API and Worker pods see the same files
- Persistent across deploys and pod restarts

## Secrets

Stored in **AWS Secrets Manager**, synced into the cluster by the External Secrets operator. Pods read them as plain env vars (`envFrom: secretRef`).

| Purpose | Secret name (prod) |
|---|---|
| App env vars | `ctdl-xtra/prod/app` |
| Redis password | `ctdl-xtra/prod/redis` |

To **add or change an app env var**, edit the app secret in Secrets Manager. Within ~5 min the External Secrets operator syncs it into the K8s `ctdl-xtra-app-env` Secret. Pods need a restart to see the change (`kubectl -n ctdl-xtra rollout restart deployment/ctdl-xtra-api deployment/ctdl-xtra-worker`).

Current keys in the app secret:
- `DATABASE_URL`
- `REDIS_URL`
- `COOKIE_KEY`
- `ENCRYPTION_KEY`
- `FRONTEND_URL`
- `CLIENT_PATH`
- `EXTRACTION_FILES_PATH`
- `NODE_ENV`
- `PORT`

## Deployments

In the `ctdl-xtra-prod` cluster's `ctdl-xtra` namespace:

| Workload | Type | Prod replicas |
|---|---|---|
| `ctdl-xtra-api` | Deployment | 2 |
| `ctdl-xtra-worker` | Deployment | 2 |
| `redis` | StatefulSet | 1 |
| `ctdl-xtra-db-migrate` | Job (one-shot per deploy) | — |

The migrate Job runs `drizzle-kit migrate` before each rollout via the deploy script.


## Deploying

> Currently paused. Release and promote workflows are disabled until SANDBOX is built. See [CI-CD.md](CI-CD.md) for context.

The intended flow (per the xTRA Design Document) is `TEST → SANDBOX → PRODUCTION`. Builds happen on merge to `main`, all promotions are manual, and images are never rebuilt between tiers.
