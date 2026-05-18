# ctdl-xtra Production EKS

Terraform for the dedicated `ctdl-xtra-prod` EKS cluster in `us-east-1`.

## Layout

- State: `s3://terraform-state-o1r8/ctdl-xtra/envs/production/tfstate`
- VPC: `10.40.0.0/16`
- Public subnets: `10.40.1.0/24`, `10.40.2.0/24`
- Private subnets: `10.40.11.0/24`, `10.40.12.0/24`
- Cluster: `ctdl-xtra-prod`
- Namespace: `ctdl-xtra`
- Service account: `ctdl-xtra`

## Commands

```bash
cd infra/terraform/envs/production
AWS_PROFILE=credreg-sso terraform init
AWS_PROFILE=credreg-sso terraform plan
```

Only apply after reviewing the plan and confirming the public API CIDR allowlist in `terraform.tfvars`.
