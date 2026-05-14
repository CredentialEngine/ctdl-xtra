data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  oidc_provider_url = replace(aws_iam_openid_connect_provider.this.url, "https://", "")
}

resource "aws_kms_key" "cluster_secrets" {
  count = var.enable_cluster_secret_encryption ? 1 : 0

  description             = "EKS secret encryption key for ${var.cluster_name}"
  deletion_window_in_days = var.cluster_kms_deletion_window_days
  enable_key_rotation     = true

  tags = merge(var.common_tags, {
    Name = "${var.cluster_name}-eks-secrets"
  })
}

resource "aws_kms_alias" "cluster_secrets" {
  count = var.enable_cluster_secret_encryption ? 1 : 0

  name          = "alias/${var.cluster_name}-eks-secrets"
  target_key_id = aws_kms_key.cluster_secrets[0].key_id
}

resource "aws_eks_cluster" "this" {
  name     = var.cluster_name
  role_arn = aws_iam_role.cluster.arn
  version  = var.cluster_version

  access_config {
    authentication_mode                         = var.authentication_mode
    bootstrap_cluster_creator_admin_permissions = var.bootstrap_cluster_creator_admin_permissions
  }

  enabled_cluster_log_types = [
    "api",
    "audit",
    "authenticator",
    "controllerManager",
    "scheduler"
  ]

  dynamic "encryption_config" {
    for_each = var.enable_cluster_secret_encryption ? [1] : []

    content {
      provider {
        key_arn = aws_kms_key.cluster_secrets[0].arn
      }
      resources = ["secrets"]
    }
  }

  kubernetes_network_config {
    service_ipv4_cidr = var.cluster_service_ipv4_cidr
  }

  vpc_config {
    endpoint_private_access = var.cluster_endpoint_private_access
    endpoint_public_access  = var.cluster_endpoint_public_access
    public_access_cidrs     = var.cluster_endpoint_public_access_cidrs
    subnet_ids              = var.private_subnet_ids
  }

  tags = merge(var.common_tags, {
    Name = var.cluster_name
  })

  depends_on = [
    aws_iam_role_policy_attachment.cluster_amazon_eks_cluster_policy,
    aws_iam_role_policy_attachment.cluster_amazon_eks_vpc_resource_controller
  ]
}

resource "aws_iam_openid_connect_provider" "this" {
  client_id_list  = ["sts.${data.aws_partition.current.dns_suffix}"]
  thumbprint_list = [var.eks_oidc_root_ca_thumbprint]
  url             = aws_eks_cluster.this.identity[0].oidc[0].issuer

  tags = merge(var.common_tags, {
    Name = "${var.cluster_name}-eks-irsa"
  })
}

resource "aws_eks_access_entry" "cluster_admin" {
  for_each = toset(var.cluster_admin_principal_arns)

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "cluster_admin" {
  for_each = toset(var.cluster_admin_principal_arns)

  cluster_name  = aws_eks_cluster.this.name
  principal_arn = each.value
  policy_arn    = "arn:${data.aws_partition.current.partition}:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.cluster_admin]
}
