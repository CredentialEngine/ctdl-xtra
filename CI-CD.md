# CI/CD Pipeline

## Branching Model

```
feature/* or fix/*
       │
       │  Pull Request
       ▼
     main  ──────────────────────────────────────────────────────────►  git history
       │
       │  Merge to main (automatic)
       ▼
  [Release workflow]
  Build images → push to STAGING ECR
       │
       │  Manual trigger
       ▼
  [Promote to STAGING]
  envsubst + kubectl apply → ctdl-xtra-staging cluster
       │
       │  Manual trigger (exact sha tag required)
       ▼
  [Promote to PRODUCTION]
  Copy image STAGING ECR → PRODUCTION ECR (no rebuild)
  envsubst + kubectl apply → ctdl-xtra-prod cluster
```

All development happens on short-lived branches off `main`. There is no long-lived staging or release branch — environment promotion is controlled through GitHub Actions workflows, not through git branches.

---

## Workflows

### CI (`ci.yml`) — Pull Request

Runs on every PR. Blocks merge if any job fails.

| Job | What it does |
|-----|-------------|
| Lint | ESLint on the `client/` workspace |
| Test | Vitest on the `server/` workspace |
| Build images | Docker build for API and Worker (no push, uses GHA layer cache) |

### Build Base Image (`build-base.yml`) — Push to `main` (path-filtered)

Triggers only when `base.Dockerfile` changes. Builds the shared base image (system Chrome, fonts, pm2, pnpm, pre-downloaded Chrome binaries) and pushes to `ctdl-xtra-staging/base:latest`. Both `Dockerfile` and `worker.Dockerfile` `FROM` this base, so app builds skip the heavy apt + Chrome install.

### Release (`release.yml`) — Push to `main`

Runs automatically on every merge to `main`. Lint and Test run in parallel (non-blocking via `continue-on-error`); `publish` runs independently.

Produces two image tags per service and pushes to STAGING ECR:

| Tag | Purpose |
|-----|---------|
| `sha-<7char>` | Immutable reference to this exact commit, used for promotion |
| `main-latest` | Floating tag, always points to the latest main build |

ECR repositories written to:
- `ctdl-xtra-staging/api`
- `ctdl-xtra-staging/worker`

### Promote to STAGING (`promote-staging.yml`) — Manual

Go to **Actions → Promote to STAGING → Run workflow**.

Input: `image_tag` (default: `main-latest`). Use a `sha-*` tag to deploy a specific commit.

Runs `deploy-app.sh` with `IMAGE_TAG` set, which `envsubst`s the tag into `deployment.yaml` / `db-migrate-job.yaml` and `kubectl apply`s the full manifest set on `ctdl-xtra-staging`.

### Promote to PRODUCTION (`promote-production.yml`) — Manual

Go to **Actions → Promote to PRODUCTION → Run workflow**.

Input: `image_tag` (**required**, must be an exact `sha-*` tag).

Steps:
1. Validates the tag exists in STAGING ECR.
2. Copies the image manifest via the ECR API (no Docker pull/push, same digest guaranteed) to PRODUCTION ECR under the same `sha-*` tag.
3. Runs `deploy-app.sh` against `ctdl-xtra-prod` — same envsubst + apply flow as staging.

ECR repositories written to:
- `ctdl-xtra/api`
- `ctdl-xtra/worker`

---

## Deployment Model

Manifests in `infra/terraform/k8s-manifests/{staging,production}/app/` are **templates**, not state snapshots. The image reference is left as a placeholder:

```yaml
image: 996810415034.dkr.ecr.us-east-1.amazonaws.com/ctdl-xtra/api:${IMAGE_TAG}
```

At deploy time, `deploy-app.sh` substitutes `${IMAGE_TAG}` with the requested tag and applies the manifest. Consequences:

- **Cluster state = last successful workflow run.** Workflow run history is deployment history.
- **No `kubectl set image`.** Apply is the only deployment mechanism, so manifest edits (resource limits, env vars, probes) flow through the same path as image changes.
- **No git commits from CI.** The manifest stays a template; the tag lives in the workflow input.
- **Disaster recovery is trivial.** Re-run the workflow with the desired sha.
- **You cannot `kubectl apply -f` the manifest directly** — it must go through `envsubst` (or via `bash deploy-app.sh` with `IMAGE_TAG` set).

---

## Key Principles

- **Build once.** Images are built only on merge to `main`. Promotion to production copies the manifest via the AWS ECR API; the image is never rebuilt and the digest never changes.
- **Immutable tags.** `sha-*` tags are never overwritten. Only `main-latest` floats (staging only).
- **Specific sha in production.** Production deploys always specify an exact `sha-*` tag.
- **Manual gates.** Both staging and production deploys require a human to trigger them in GitHub Actions.
- **OIDC auth.** GitHub Actions assumes the `ctdl-xtra-github-actions-ci` IAM role via OIDC (no stored AWS credentials). The role ARN is stored as the `AWS_ROLE_ARN` repository secret.

---

## Infrastructure

| Environment | EKS Cluster | ECR prefix | Domain |
|-------------|-------------|------------|--------|
| Staging | `ctdl-xtra-staging` | `ctdl-xtra-staging/*` | `xtra-staging.credentialengineregistry.org` |
| Production | `ctdl-xtra-prod` | `ctdl-xtra/*` | `xtra.credentialengineregistry.org` |

Terraform for the IAM role and OIDC provider lives in [`infra/terraform/github-ci-oidc/`](infra/terraform/github-ci-oidc/).
