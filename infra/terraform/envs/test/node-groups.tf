# TEST runs on a single consolidated node group (no HA — fail-fast by design).
# The launch template raises kubelet max-pods to 110 so one t3.medium can host
# the full workload once VPC CNI prefix delegation is enabled (see main.tf).
resource "aws_launch_template" "node" {
  name_prefix = "${local.cluster_name}-node-"

  # AL2023 NodeConfig merged by the managed node group bootstrap.
  user_data = base64encode(<<-EOT
    MIME-Version: 1.0
    Content-Type: multipart/mixed; boundary="//"

    --//
    Content-Type: application/node.eks.aws

    ---
    apiVersion: node.eks.aws/v1alpha1
    kind: NodeConfig
    spec:
      kubelet:
        config:
          maxPods: 110
    --//--
  EOT
  )

  tags = local.common_tags

  lifecycle {
    create_before_destroy = true
  }
}

# Single node group for TEST. Kept as resource "app" (not renamed) so changing
# the launch template triggers an in-place EKS rolling node update rather than a
# destroy/recreate of the node group.
resource "aws_eks_node_group" "app" {
  cluster_name    = module.eks.cluster_id
  node_group_name = "${local.cluster_name}-app"
  node_role_arn   = module.eks.nodegroup_role_arn
  subnet_ids      = module.vpc.private_subnet_ids

  ami_type      = "AL2023_x86_64_STANDARD"
  capacity_type = "ON_DEMAND"

  instance_types = var.app_node_instance_types

  launch_template {
    id      = aws_launch_template.node.id
    version = aws_launch_template.node.latest_version
  }

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

  # Rolling node replacement on launch-template changes.
  update_config {
    max_unavailable = 1
  }

  lifecycle {
    ignore_changes = [
      scaling_config[0].desired_size
    ]
  }

  tags = local.common_tags

  depends_on = [module.vpc]
}
