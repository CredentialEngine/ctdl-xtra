# GitHub Actions OIDC

This creates the IAM role used by GitHub Actions to push CTDL xTRA images to ECR without static AWS keys.

The trust policy is scoped to:

```text
repo:CredentialEngine/ctdl-xtra:*
```

Apply:

```bash
cd infra/terraform/github-ci-oidc
terraform init
terraform apply
```

Then add the `role_arn` output as the GitHub Actions repository secret:

```text
AWS_ROLE_ARN
```

The role can push only to:

```text
ctdl-xtra-app
ctdl-xtra-worker
```

The account-level GitHub OIDC provider must already exist at:

```text
https://token.actions.githubusercontent.com
```
