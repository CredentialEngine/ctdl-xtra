# PROD single-AZ topology (us-east-1a): one system node + one app node.
# No cross-AZ HA at this stage (accepted trade-off).

# Launch template for the system node group only: a single t3.medium must host
# all platform pods, which exceeds the default 17-pod cap, so raise kubelet
# max-pods to 110 (works together with VPC CNI prefix delegation, see main.tf).
# The app node (t3.large) stays on the default cap (~35) — it runs few pods.
resource "aws_launch_template" "system" {
  name_prefix = "${local.cluster_name}-system-"

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size = var.system_node_disk_size
      volume_type = "gp3"
      encrypted   = true
    }
  }

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

resource "aws_eks_node_group" "system" {
  cluster_name    = module.eks.cluster_id
  node_group_name = "${local.cluster_name}-system"
  node_role_arn   = module.eks.nodegroup_role_arn
  subnet_ids      = local.single_az_private_subnet_ids

  ami_type       = "AL2023_x86_64_STANDARD"
  capacity_type  = "ON_DEMAND"
  instance_types = var.system_node_instance_types

  launch_template {
    id      = aws_launch_template.system.id
    version = aws_launch_template.system.latest_version
  }

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

  tags = local.common_tags

  depends_on = [module.vpc]
}

resource "aws_eks_node_group" "app" {
  cluster_name    = module.eks.cluster_id
  node_group_name = "${local.cluster_name}-app"
  node_role_arn   = module.eks.nodegroup_role_arn
  subnet_ids      = local.single_az_private_subnet_ids

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

  tags = local.common_tags

  depends_on = [module.vpc]
}
