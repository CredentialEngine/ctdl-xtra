resource "aws_eks_node_group" "system" {
  cluster_name    = module.eks.cluster_id
  node_group_name = "${local.cluster_name}-system"
  node_role_arn   = module.eks.nodegroup_role_arn
  subnet_ids      = module.vpc.private_subnet_ids

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  disk_size      = var.system_node_disk_size
  instance_types = var.system_node_instance_types

  labels = {
    env      = local.env
    nodepool = "system"
  }

  scaling_config {
    desired_size = var.system_node_desired_size
    max_size     = var.system_node_max_size
    min_size     = var.system_node_min_size
  }

  update_config {
    max_unavailable = 1
  }

  lifecycle {
    ignore_changes = [
      scaling_config[0].desired_size
    ]
  }

  tags = merge(local.common_tags, {
    "k8s.io/cluster-autoscaler/${local.cluster_name}" = "owned"
    "k8s.io/cluster-autoscaler/enabled"               = "true"
  })

  depends_on = [module.vpc]
}

resource "aws_eks_node_group" "app" {
  cluster_name    = module.eks.cluster_id
  node_group_name = "${local.cluster_name}-app"
  node_role_arn   = module.eks.nodegroup_role_arn
  subnet_ids      = module.vpc.private_subnet_ids

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  disk_size      = var.app_node_disk_size
  instance_types = var.app_node_instance_types

  labels = {
    env      = local.env
    nodepool = "app"
    workload = local.project_name
  }

  scaling_config {
    desired_size = var.app_node_desired_size
    max_size     = var.app_node_max_size
    min_size     = var.app_node_min_size
  }

  update_config {
    max_unavailable = 1
  }

  lifecycle {
    ignore_changes = [
      scaling_config[0].desired_size
    ]
  }

  tags = merge(local.common_tags, {
    "k8s.io/cluster-autoscaler/${local.cluster_name}" = "owned"
    "k8s.io/cluster-autoscaler/enabled"               = "true"
  })

  depends_on = [module.vpc]
}
