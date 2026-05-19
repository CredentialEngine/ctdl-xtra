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
  Build images → push to TEST ECR
       │
       │  Automatic (workflow_run on Release success)
       ▼
  [Deploy to TEST]
  envsubst + kubectl apply → ctdl-xtra-test cluster
       │
       │  Manual trigger
       ▼
  [Promote to SANDBOX]
  Copy image TEST ECR → SANDBOX ECR (no rebuild)
  envsubst + kubectl apply → ctdl-xtra-sandbox cluster
       │
       │  Manual trigger (exact sha tag required)
       ▼
  [Promote to PRODUCTION]
  Copy image SANDBOX ECR → PRODUCTION ECR (no rebuild)
  envsubst + kubectl apply → ctdl-xtra-prod cluster
```

All development happens on short-lived branches off `main`. There is no long-lived branch — environment promotion is controlled through GitHub Actions workflows, not through git branches.

This mirrors the environment model in the xTRA Design Document: `DEVELOPMENT → TEST → SANDBOX → PRODUCTION`.

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

Triggers only when `base.Dockerfile` changes. Builds the shared base image (system Chrome, fonts, pm2, pnpm, pre-downloaded Chrome binaries) and pushes to `ctdl-xtra-test/base:latest`. Both `Dockerfile` and `worker.Dockerfile` `FROM` this base, so app builds skip the heavy apt + Chrome install.

The base image lives in TEST's ECR namespace because that's where builds happen. SANDBOX and PRODUCTION never pull from it — base layers are baked into the api/worker image manifests at `docker build` time, so promoted images are self-contained.

### Release (`release.yml`) — Push to `main`

Runs automatically on every merge to `main`. Lint and Test run in parallel (non-blocking via `continue-on-error`); `publish` runs independently.

Produces two image tags per service and pushes to TEST ECR:

| Tag | Purpose |
|-----|---------|
| `sha-<7char>` | Immutable reference to this exact commit, used for promotion |
| `main-latest` | Floating tag, always points to the latest main build |

ECR repositories written to:
- `ctdl-xtra-test/api`
- `ctdl-xtra-test/worker`

### Deploy to TEST (`deploy-test.yml`) — Automatic on Release success

Triggered by `workflow_run` after `Release` completes successfully (also runnable manually via `workflow_dispatch`). Resolves the EFS file system id for `ctdl-xtra-test-files` and runs `deploy-app.sh` against the `ctdl-xtra-test` cluster. The deploy target is the same `sha-<7char>` tag the release just produced.

This is the "automatic when possible" deployment the design doc specifies for TEST.

### Promote to SANDBOX (`promote-sandbox.yml`) — Manual

Go to **Actions → Promote to SANDBOX → Run workflow**.

Input: `image_tag` (**required**, must be an exact `sha-*` tag).

Steps:
1. `crane copy` the image manifest+layers from TEST ECR to SANDBOX ECR under the same `sha-*` tag.
2. Runs `deploy-app.sh` against `ctdl-xtra-sandbox` — envsubst + apply.

### Promote to PRODUCTION (`promote-production.yml`) — Manual

Go to **Actions → Promote to PRODUCTION → Run workflow**.

Input: `image_tag` (**required**, must be an exact `sha-*` tag).

Steps:
1. `crane copy` the image manifest+layers from SANDBOX ECR to PRODUCTION ECR under the same `sha-*` tag.
2. Runs `deploy-app.sh` against `ctdl-xtra-prod` — envsubst + apply.

ECR repositories written to:
- `ctdl-xtra/api`
- `ctdl-xtra/worker`

---

## Deployment Model

Manifests in `infra/terraform/k8s-manifests/{test,sandbox,production}/app/` are **templates**, not state snapshots. The image reference is left as a placeholder:

```yaml
image: 996810415034.dkr.ecr.us-east-1.amazonaws.com/ctdl-xtra/api:${IMAGE_TAG}
```

At deploy time, `deploy-app.sh` substitutes `${IMAGE_TAG}` with the requested tag and applies the manifest. TEST and SANDBOX additionally template `${EFS_FS_ID}` in `storage.yaml`. Consequences:

- **Cluster state = last successful workflow run.** Workflow run history is deployment history.
- **No `kubectl set image`.** Apply is the only deployment mechanism, so manifest edits (resource limits, env vars, probes) flow through the same path as image changes.
- **No git commits from CI.** The manifest stays a template; the tag lives in the workflow input.
- **Disaster recovery is trivial.** Re-run the workflow with the desired sha.
- **You cannot `kubectl apply -f` the manifest directly** — it must go through `envsubst` (or via `bash deploy-app.sh` with required env vars set).

---

## Key Principles

- **Build once.** Images are built only on merge to `main`. Every promotion copies via `crane`; the image is never rebuilt and the digest never changes from TEST through PRODUCTION.
- **Immutable tags.** `sha-*` tags are never overwritten. Only `main-latest` floats (TEST only).
- **Specific sha in production.** Production deploys always specify an exact `sha-*` tag.
- **Manual gates above TEST.** TEST auto-deploys; SANDBOX and PRODUCTION require a human to trigger.
- **OIDC auth.** GitHub Actions assumes the `ctdl-xtra-github-actions-ci` IAM role via OIDC (no stored AWS credentials). The role ARN is stored as the `AWS_ROLE_ARN` repository secret.

---

## Infrastructure

| Environment | EKS Cluster | ECR prefix | Domain |
|-------------|-------------|------------|--------|
| Test | `ctdl-xtra-test` | `ctdl-xtra-test/*` | `xtra-test.credentialengineregistry.org` |
| Sandbox | `ctdl-xtra-sandbox` | `ctdl-xtra-sandbox/*` | `xtra-sandbox.credentialengineregistry.org` |
| Production | `ctdl-xtra-prod` | `ctdl-xtra/*` | `xtra.credentialengineregistry.org` |

Terraform for the IAM role and OIDC provider lives in [`infra/terraform/github-ci-oidc/`](infra/terraform/github-ci-oidc/).
