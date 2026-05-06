# CTDL xTRA Infrastructure

This directory contains the infrastructure used to run CTDL xTRA on the
`cer-api-prod` EKS cluster in `us-east-1`.

## Deployed AWS Resources

The main stack is in `envs/ctdl-xtra` and uses the shared S3 backend:

- bucket: `terraform-state-o1r8`
- key: `ctdl-xtra/envs/ctdl-xtra/tfstate`

It provisions:

- An EKS managed node group named `ctdl-xtra`.
  - Cluster: `cer-api-prod`
  - Instance type: `m6i.large`
  - Capacity: on-demand
  - Scaling: min `1`, desired `1`, max `2`
  - Label: `workload=ctdl-xtra`
  - Taint: `workload=ctdl-xtra:NoSchedule`
- ECR repositories:
  - `ctdl-xtra-app`
  - `ctdl-xtra-worker`
- Secrets Manager secret:
  - `ctdl-xtra`
- EFS filesystem and mount targets for shared app storage.

The stack discovers the existing EKS VPC, private subnets, node security groups,
cluster, and node group IAM role from the existing `cer-api-prod` infrastructure.

## GitHub Actions OIDC

The `github-ci-oidc` stack provisions the GitHub Actions IAM role used by the
image build workflow.

It uses backend key:

- `ctdl-xtra/github-ci-oidc/tfstate`

The deployed role is:

- `github-actions-ctdl-xtra`

The role is trusted by GitHub OIDC for `CredentialEngine/ctdl-xtra` and can push
images to the CTDL xTRA app and worker ECR repositories. Store its ARN in the
repository secret `AWS_ROLE_ARN`.

## Kubernetes Manifests

Kubernetes resources live under `k8s-manifests/ctdl-xtra`.

They define:

- Namespace: `ctdl-xtra`
- ServiceAccount: `ctdl-xtra`
- ExternalSecret syncing from Secrets Manager secret `ctdl-xtra`
- ConfigMap for non-secret runtime configuration
- EFS-backed shared PVC: `ctdl-xtra-storage`
- Redis StatefulSet, Service, and ConfigMap
- Database migration Job
- Web Deployment and Service
- Worker Deployment
- NGINX Ingress with cert-manager TLS

The current public hostname is:

- `ctdl-xtra.credentialengineregistry.org`

The app and worker deployments are pinned to the CTDL node group through the
`workload=ctdl-xtra` node selector and matching toleration.

## Live Dependencies

These resources are part of the current deployment but are not fully represented
in this Terraform directory yet:

- RDS clone: `aicrawler-ctdl-xtra`
  - Created from the original `aicrawler` database
  - Placed in the EKS VPC using DB subnet group `cer-api-app-db-subnet-group`
  - Used by `DATABASE_URL` in Secrets Manager secret `ctdl-xtra`
- RDS security group: `ctdl-xtra-rds`
  - Allows PostgreSQL from EKS workloads
- EKS managed add-on: `aws-efs-csi-driver`
  - Required for the EFS-backed RWX PVC
- Route53 CNAME:
  - `ctdl-xtra.credentialengineregistry.org`
  - Points to the NGINX ingress load balancer

## Image Build Workflow

The GitHub Actions workflow at `.github/workflows/build-images.yml` builds and
pushes the app and worker images to ECR.

It runs for matching changes on:

- `main`
- `preview`

It also supports manual `workflow_dispatch`.

The currently deployed workload uses the `preview` image tags.
