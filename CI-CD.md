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
  Deploy to ctdl-xtra-staging cluster
       │
       │  Manual trigger (exact sha tag required)
       ▼
  [Promote to PRODUCTION]
  Copy image STAGING ECR → PRODUCTION ECR (no rebuild)
  Deploy to ctdl-xtra-prod cluster
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

### Release (`release.yml`) — Push to `main`

Runs automatically on every merge to `main`. Lint and Test must pass before the publish step runs.

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

Deploys to the `ctdl-xtra-staging` EKS cluster, waits for rollout completion (5 min timeout).

### Promote to PRODUCTION (`promote-production.yml`) — Manual

Go to **Actions → Promote to PRODUCTION → Run workflow**.

Input: `image_tag` (**required**, must be an exact `sha-*` tag — no default).

Steps:
1. Validates the tag exists in STAGING ECR.
2. Copies the image manifest via the ECR API (no Docker pull/push, same digest guaranteed) to PRODUCTION ECR under both `sha-*` and `prod-latest` tags.
3. Deploys to the `ctdl-xtra-prod` EKS cluster, waits for rollout completion.

ECR repositories written to:
- `ctdl-xtra/api`
- `ctdl-xtra/worker`

---

## Key Principles

- **Build once** — images are built only on merge to `main`. Promoting to production copies the manifest via the AWS ECR API; the image is never rebuilt and the digest never changes.
- **Immutable tags** — `sha-*` tags are never overwritten. Only `main-latest` and `prod-latest` float.
- **Manual gates** — both staging and production deploys require a human to pull the trigger in GitHub Actions. There is no auto-deploy to any environment.
- **OIDC auth** — GitHub Actions assumes the `ctdl-xtra-github-actions-ci` IAM role via OIDC (no stored AWS credentials). The role ARN is stored as the `AWS_ROLE_ARN` repository secret.

---

## Infrastructure

| Environment | EKS Cluster | ECR prefix | Domain |
|-------------|-------------|------------|--------|
| Staging | `ctdl-xtra-staging` | `ctdl-xtra-staging/*` | `xtra-staging.credentialengineregistry.org` |
| Production | `ctdl-xtra-prod` | `ctdl-xtra/*` | `xtra.credentialengineregistry.org` |

Terraform for the IAM role and OIDC provider lives in [`infra/terraform/github-ci-oidc/`](infra/terraform/github-ci-oidc/).
