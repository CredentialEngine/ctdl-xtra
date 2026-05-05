resource "aws_eks_node_group" "ctdl_xtra" {
  cluster_name    = data.aws_eks_cluster.cluster.name
  node_group_name = "ctdl-xtra"
  node_role_arn   = data.aws_iam_role.eks_nodegroup_role.arn
  subnet_ids      = data.aws_subnets.private.ids

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  disk_size      = 50
  instance_types = var.node_group_instance_types

  scaling_config {
    desired_size = var.node_group_desired_size
    min_size     = var.node_group_min_size
    max_size     = var.node_group_max_size
  }

  labels = {
    workload = local.project_name
  }

  taint {
    key    = "workload"
    value  = local.project_name
    effect = "NO_SCHEDULE"
  }

  lifecycle {
    ignore_changes = [
      scaling_config[0].desired_size
    ]
  }

  update_config {
    max_unavailable = 1
  }

  tags = merge(
    local.common_tags,
    {
      "k8s.io/cluster-autoscaler/${var.eks_cluster_name}" = "owned"
      "k8s.io/cluster-autoscaler/enabled"                 = "true"
    }
  )
}
