# CI/CD Pipeline

> **Status:** the `staging` environment was decommissioned. Until SANDBOX is built, the `Release`, `Build Base Image`, and `Promote to PRODUCTION` workflows are disabled (manual-only via `workflow_dispatch`, with no working ECR targets). The `CI` workflow on PRs still runs.
>
> The design target (per the xTRA Design Document) is `TEST → SANDBOX → PRODUCTION`.

## Branching Model (target)

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
  Build images → push to TEST ECR     (not yet wired)
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

### Build Base Image (`build-base.yml`) — Disabled

Built the shared base image (system Chrome, fonts, pm2, pnpm, pre-downloaded Chrome binaries). Pushed to `ctdl-xtra-staging/base:latest`, which no longer exists. The base will move to an env-neutral ECR repo when SANDBOX is built.

### Release (`release.yml`) — Disabled

Will resume building `sha-<7char>` images on every merge to `main` and pushing them to SANDBOX (or TEST, when that tier exists). Currently `workflow_dispatch` only.

### Promote to PRODUCTION (`promote-production.yml`) — Disabled in practice

Manual only; copies an image from the pre-prod ECR to `ctdl-xtra/{api,worker}` using `crane copy` and deploys via `deploy-app.sh`. The source repo will be repointed to `ctdl-xtra-sandbox/*` once SANDBOX is built.

---

## Deployment Model

Manifests in `infra/terraform/k8s-manifests/production/app/` are **templates**, not state snapshots. The image reference is left as a placeholder:

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

- **Build once.** Images are built only on merge to `main`. Promotion copies via the AWS ECR API (`crane copy`); the image is never rebuilt and the digest never changes.
- **Immutable tags.** `sha-*` tags are never overwritten.
- **Specific sha in production.** Production deploys always specify an exact `sha-*` tag.
- **Manual gates.** Both pre-prod and production deploys require a human to trigger them in GitHub Actions.
- **OIDC auth.** GitHub Actions assumes the `ctdl-xtra-github-actions-ci` IAM role via OIDC (no stored AWS credentials). The role ARN is stored as the `AWS_ROLE_ARN` repository secret.

---

## Infrastructure

| Environment | EKS Cluster | ECR prefix | Domain |
|-------------|-------------|------------|--------|
| Production | `ctdl-xtra-prod` | `ctdl-xtra/*` | `xtra.credentialengineregistry.org` |

Terraform for the IAM role and OIDC provider lives in [`infra/terraform/github-ci-oidc/`](infra/terraform/github-ci-oidc/).
