locals {
  project_name = "ctdl-xtra"
  namespace    = "ctdl-xtra"

  common_tags = {
    project = local.project_name
    cluster = var.eks_cluster_name
  }
}

module "ecr" {
  source = "../../modules/ecr"

  repository_names = [
    "${local.project_name}-app",
    "${local.project_name}-worker",
  ]
  common_tags = local.common_tags
}

module "ctdl_xtra_secret" {
  source = "../../modules/secrets"

  secret_name   = local.project_name
  description   = "CTDL xTRA application secrets"
  secret_values = var.ctdl_xtra_secret_values
  tags          = local.common_tags
}

module "efs" {
  source = "../../modules/efs"

  name                       = local.project_name
  vpc_id                     = data.aws_vpc.main.id
  subnet_ids                 = toset(data.aws_subnets.private.ids)
  allowed_security_group_ids = toset(data.aws_security_groups.eks_nodes.ids)
  common_tags                = local.common_tags
}
