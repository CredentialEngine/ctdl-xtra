data "aws_vpc" "main" {
  tags = {
    project = "cer-api"
  }
}

data "aws_subnets" "private" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }

  filter {
    name   = "tag:Name"
    values = ["app_vpc-private-*"]
  }
}

data "aws_eks_cluster" "cluster" {
  name = var.eks_cluster_name
}

data "aws_iam_role" "eks_nodegroup_role" {
  name = var.eks_nodegroup_role_name
}

data "aws_security_groups" "eks_nodes" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }

  tags = {
    "kubernetes.io/cluster/${var.eks_cluster_name}" = "owned"
  }
}
