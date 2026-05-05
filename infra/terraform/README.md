# CTDL xTRA Infrastructure

This directory follows the `ce-registry/infra` layout:

- `envs/ctdl-xtra`: Terraform for AWS resources attached to the target EKS cluster in `us-east-1`.
- `github-ci-oidc`: Terraform for the GitHub Actions IAM role used by the image build workflow.
- `modules`: small reusable Terraform modules.
- `k8s-manifests/ctdl-xtra`: Kubernetes manifests for the CTDL xTRA namespace and workloads.

The first target is a Cloud66-to-EKS migration with:

- dedicated namespace: `ctdl-xtra`
- dedicated node group: `ctdl-xtra`
- app deployment: `ctdl-xtra-web`
- worker deployment: `ctdl-xtra-worker`
- shared extraction storage: EFS mounted at `/app/storage`
- secrets sourced from AWS Secrets Manager through External Secrets

Do not commit real Cloud66 secret values. Rotate the source credentials and update the `ctdl-xtra` secret directly in AWS Secrets Manager.
