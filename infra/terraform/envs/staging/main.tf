locals {
  project_name = "ctdl-xtra"
  env          = "staging"
  cluster_name = "${local.project_name}-${local.env}"

  common_tags = {
    project     = local.project_name
    environment = local.env
    managed-by  = "terraform"
  }
}

# ---------------------------------------------------------------
# Networking
# ---------------------------------------------------------------

module "vpc" {
  source = "../../modules/vpc"

  name                   = local.cluster_name
  vpc_cidr               = var.vpc_cidr
  public_subnet_cidrs    = var.public_subnet_cidrs
  private_subnet_cidrs   = var.private_subnet_cidrs
  azs                    = var.azs
  single_nat_gateway     = var.single_nat_gateway
  nat_eip_allocation_ids = var.nat_eip_allocation_ids
  enable_flow_logs       = var.enable_vpc_flow_logs
  common_tags            = local.common_tags

  public_subnet_tags = {
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
    "kubernetes.io/role/elb"                      = "1"
  }

  private_subnet_tags = {
    "kubernetes.io/cluster/${local.cluster_name}" = "shared"
    "kubernetes.io/role/internal-elb"             = "1"
  }
}

# ---------------------------------------------------------------
# EKS
# ---------------------------------------------------------------

module "eks" {
  source = "../../modules/eks"

  cluster_name                                = local.cluster_name
  cluster_version                             = var.cluster_version
  cluster_service_ipv4_cidr                   = var.cluster_service_ipv4_cidr
  cluster_endpoint_private_access             = var.cluster_endpoint_private_access
  cluster_endpoint_public_access              = var.cluster_endpoint_public_access
  cluster_endpoint_public_access_cidrs        = var.cluster_endpoint_public_access_cidrs
  authentication_mode                         = var.authentication_mode
  bootstrap_cluster_creator_admin_permissions = var.bootstrap_cluster_creator_admin_permissions
  cluster_admin_principal_arns                = var.cluster_admin_principal_arns
  enable_cluster_secret_encryption            = var.enable_cluster_secret_encryption
  private_subnet_ids                          = module.vpc.private_subnet_ids
  route53_hosted_zone_id                      = var.route53_hosted_zone_id
  app_namespace                               = var.app_namespace
  additional_app_namespaces                   = var.additional_app_namespaces
  app_service_account                         = var.app_service_account
  application_irsa_role_name                  = "${local.cluster_name}-application-irsa-role"
  application_irsa_policy_name                = "${local.cluster_name}-application-s3-policy"
  application_s3_bucket_names                 = var.application_s3_bucket_names
  external_secrets_secret_name_prefixes       = var.external_secrets_secret_name_prefixes
  external_secrets_ssm_parameter_prefixes     = var.external_secrets_ssm_parameter_prefixes
  enable_efs_csi_driver                       = var.enable_efs_csi_driver
  common_tags                                 = local.common_tags
}
