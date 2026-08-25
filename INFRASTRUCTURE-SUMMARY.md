# Infrastructure Summary

Quick reference for app developers — endpoints, names, and how to find/change things in each environment.

The environment chain follows the xTRA Design Document: `DEVELOPMENT → TEST → SANDBOX → PRODUCTION`.

## Environments

| | Test | Sandbox | Production |
|---|---|---|---|
| **App URL** | `https://xtra-test.credentialengineregistry.org` | `https://xtra-sandbox.credentialengineregistry.org` | `https://xtra.credentialengineregistry.org` |
| **EKS cluster** | `ctdl-xtra-test` | `ctdl-xtra-sandbox` | `ctdl-xtra-prod` |
| **K8s namespace** | `ctdl-xtra` | `ctdl-xtra` | `ctdl-xtra` |
| **VPC CIDR** | `10.42.0.0/16` | `10.41.0.0/16` | `10.40.0.0/16` |
| **AWS region** | `us-east-1` | `us-east-1` | `us-east-1` |
| **AWS account** | `996810415034` | `996810415034` | `996810415034` |

## Container images (ECR)

| | Test | Sandbox | Production |
|---|---|---|---|
| API repo | `ctdl-xtra-test/api` | `ctdl-xtra-sandbox/api` | `ctdl-xtra/api` |
| Worker repo | `ctdl-xtra-test/worker` | `ctdl-xtra-sandbox/worker` | `ctdl-xtra/worker` |
| Base image | `ctdl-xtra-test/base` (owned by test; built once, consumed by Dockerfiles at build time) | N/A — base layers are embedded in the promoted api/worker images | N/A — same |
| Image tag pattern | `sha-<7char>`, `main-latest` (floats) | `sha-<7char>` only (crane-copied from test) | `sha-<7char>` only (crane-copied from sandbox) |

All images are at `996810415034.dkr.ecr.us-east-1.amazonaws.com/<repo>:<tag>`. Promotion never rebuilds — each tier is the byte-for-byte same image as the tier upstream.

## Database (RDS PostgreSQL)

| | Test | Sandbox | Production |
|---|---|---|---|
| Endpoint | `ctdl-xtra-test-postgres.cwdkv5tua6nq.us-east-1.rds.amazonaws.com:5432` | `ctdl-xtra-sandbox-postgres.cwdkv5tua6nq.us-east-1.rds.amazonaws.com:5432` | `ctdl-xtra-prod-postgres.cwdkv5tua6nq.us-east-1.rds.amazonaws.com:5432` |
| Instance class | `db.t4g.small` | `db.t4g.small` | `db.t4g.small` |
| DB name | `ctdl_xtra` | `ctdl_xtra` | `ctdl_xtra` |
| Engine | PostgreSQL 17.5 | PostgreSQL 17.5 | PostgreSQL 17.5 |
| HA | Single-AZ | Single-AZ | Multi-AZ |
| Reachable from | inside cluster only (private subnets) | inside cluster only (private subnets) | inside cluster only (private subnets) |

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

| | Test | Sandbox | Production |
|---|---|---|---|
| File system id | `fs-0b3bfe1beaf5ed573` | `fs-093db3f7f152e19d7` | `fs-0ade50f1051fb7502` |
| Name tag | `ctdl-xtra-test-files` | `ctdl-xtra-sandbox-files` | `ctdl-xtra-prod-files` |

`deploy-app.sh` looks up the file system id by Name tag at deploy time and substitutes it into the static PV manifest, so you don't reference the id by hand.

## Secrets

Stored in **AWS Secrets Manager**, synced into the cluster by the External Secrets operator. Pods read them as plain env vars (`envFrom: secretRef`).

| Purpose | Test | Sandbox | Prod |
|---|---|---|---|
| App env vars | `ctdl-xtra/test/app` | `ctdl-xtra/sandbox/app` | `ctdl-xtra/prod/app` |
| Redis password | `ctdl-xtra/test/redis` | `ctdl-xtra/sandbox/redis` | `ctdl-xtra/prod/redis` |

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

## Nodes

Two managed node groups per cluster (`system` and `app`), labeled `nodepool=system` and `nodepool=app`. The app group also carries `workload=ctdl-xtra`, which is the selector redis pins itself to.

| | Test | Sandbox | Production |
|---|---|---|---|
| System node group | 1× t3.medium (1-2 autoscale) | 1× t3.medium (1-2 autoscale) | 2× t3.medium (2-4 autoscale) |
| App node group | 1× t3.medium (1-2 autoscale) | 1× t3.medium (1-2 autoscale) | 2× t3.large (2-4 autoscale) |
| NAT Gateway | 1 (shared across AZs) | 1 (shared across AZs) | 1 (shared across AZs) |

Cluster autoscaler runs in each cluster and grows/shrinks the node groups based on pending pods.

## Deployments

In each cluster's `ctdl-xtra` namespace:

| Workload | Type | Test replicas | Sandbox replicas | Prod replicas |
|---|---|---|---|---|
| `ctdl-xtra-api` | Deployment | 1 | 1 | 2 |
| `ctdl-xtra-worker` | Deployment | 1 | 1 | 2 |
| `redis` | StatefulSet | 1 | 1 | 1 |
| `ctdl-xtra-db-migrate` | Job (one-shot per deploy) | — | — | — |

The migrate Job runs `drizzle-kit migrate` before each rollout via the deploy script. Test and Sandbox use lighter resource requests/limits than Production to fit on t3.medium.

## Cluster add-ons

Same five Helm/manifest installs in every cluster, all managed via `k8s-manifests/<env>/addons/install-foundation.sh`:

- **cert-manager** — TLS via Let's Encrypt (HTTP-01 / DNS-01)
- **external-secrets** — syncs AWS Secrets Manager → K8s Secrets
- **ingress-nginx** — L7 ingress + ALB
- **metrics-server** — pod/node metrics for HPA and `kubectl top`
- **cluster-autoscaler** — scales the EKS node groups based on pending pods

## Skooner dashboards

Web UI for cluster inspection. One Skooner deployment per cluster, exposed via ingress with TLS issued by cert-manager.

| | Test | Sandbox | Production |
|---|---|---|---|
| URL | `https://status.xtra-test.credentialengineregistry.org` | `https://status.xtra-sandbox.credentialengineregistry.org` | `https://status.xtra.credentialengineregistry.org` |
| Image | `ghcr.io/skooner-k8s/skooner:stable` | same | same |
| ServiceAccount | `skooner-sa` in `kube-system` | same | same |
| Baseline RBAC (always on) | `skooner-sa-view` ClusterRoleBinding → `view` | same | same |

**Logging in**: paste a short-lived ServiceAccount token. Tokens are issued by the `Generate Skooner token` workflow (manual, `workflow_dispatch`). Inputs:

- `environment` — `test` / `sandbox` / `prod` (picks the cluster)
- `duration` — `30m` / `2h` / `6h`
- `role` — applied **on top of** the baseline view:
  - `view` — removes any elevated bindings, leaves the baseline cluster-wide view in place
  - `developer` — adds a `skooner-sa-developer-edit` RoleBinding (`edit`) on the `ctdl-xtra` namespace
  - `cluster-admin` — adds a `skooner-sa-admin` ClusterRoleBinding (`cluster-admin`)
- `whitelist_source_range` — optional NGINX `whitelist-source-range` annotation (CIDR or comma-separated CIDRs)

The token is delivered via Slack (the `SLACK_WEBHOOK_URL` repo secret).

## Deploying

You don't run `kubectl` to deploy — use the GitHub Actions workflows. See [CI-CD.md](CI-CD.md) for the full pipeline. TL;DR:

- Merge to `main` → image built and pushed to test ECR → auto-deployed to test
- Run **Promote to SANDBOX** with the `sha-*` tag → image crane-copied test→sandbox and deployed
- Run **Promote to PRODUCTION** with the same `sha-*` tag → image crane-copied sandbox→prod and deployed
