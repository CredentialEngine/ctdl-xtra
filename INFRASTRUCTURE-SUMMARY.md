# Infrastructure Summary

Quick reference for app developers — endpoints, names, and how to find/change things in each environment.

## Environments

| | Staging | Production |
|---|---|---|
| **App URL** | `https://xtra-staging.credentialengineregistry.org` | `https://xtra.credentialengineregistry.org` |
| **EKS cluster** | `ctdl-xtra-staging` | `ctdl-xtra-prod` |
| **K8s namespace** | `ctdl-xtra` | `ctdl-xtra` |
| **AWS region** | `us-east-1` | `us-east-1` |
| **AWS account** | `996810415034` | `996810415034` |

## Container images (ECR)

| | Staging | Production |
|---|---|---|
| API repo | `ctdl-xtra-staging/api` | `ctdl-xtra/api` |
| Worker repo | `ctdl-xtra-staging/worker` | `ctdl-xtra/worker` |
| Base image | `ctdl-xtra-staging/base` (shared, used by both API and Worker Dockerfiles) | same |
| Image tag pattern | `sha-<7char>`, `main-latest` (floats) | `sha-<7char>` only |

All images are at `996810415034.dkr.ecr.us-east-1.amazonaws.com/<repo>:<tag>`. Promotion never rebuilds — the production image is the byte-for-byte same image as staging.

## Database (RDS PostgreSQL)

| | Staging | Production |
|---|---|---|
| Endpoint | `ctdl-xtra-staging-postgres.cwdkv5tua6nq.us-east-1.rds.amazonaws.com:5432` | `ctdl-xtra-prod-postgres.cwdkv5tua6nq.us-east-1.rds.amazonaws.com:5432` |
| DB name | `ctdl_xtra` | `ctdl_xtra` |
| Engine | PostgreSQL 17.5 | PostgreSQL 17.5 |
| HA | Single-AZ | Multi-AZ |
| Reachable from | inside cluster only (private subnets) | inside cluster only (private subnets) |

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

| Purpose | Secret name (staging) | Secret name (prod) |
|---|---|---|
| App env vars | `ctdl-xtra/staging/app` | `ctdl-xtra/prod/app` |
| Redis password | `ctdl-xtra/staging/redis` | `ctdl-xtra/prod/redis` |

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

In each cluster's `ctdl-xtra` namespace:

| Workload | Type | Staging replicas | Prod replicas |
|---|---|---|---|
| `ctdl-xtra-api` | Deployment | 1 | 2 |
| `ctdl-xtra-worker` | Deployment | 1 | 2 |
| `redis` | StatefulSet | 1 | 1 |
| `ctdl-xtra-db-migrate` | Job (one-shot per deploy) | — | — |

The migrate Job runs `drizzle-kit migrate` before each rollout via the deploy script.


## Deploying

You don't run `kubectl` to deploy — use the GitHub Actions workflows. See [CI-CD.md](CI-CD.md) for the full pipeline. TL;DR:

- Merge to `main` → image auto-built and pushed to staging ECR
- Run **Promote to STAGING** workflow → image deployed to staging cluster
- Run **Promote to PRODUCTION** workflow with the same `sha-*` tag → same image copied to prod ECR and deployed

