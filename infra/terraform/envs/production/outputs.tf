output "cluster_name" {
  description = "Production EKS cluster name."
  value       = module.eks.cluster_id
}

output "cluster_endpoint" {
  description = "Production EKS API endpoint."
  value       = module.eks.cluster_endpoint
}

output "cluster_oidc_issuer_url" {
  description = "Production EKS OIDC issuer URL."
  value       = module.eks.cluster_oidc_issuer_url
}

output "vpc_id" {
  description = "Production VPC ID."
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "Production VPC CIDR block."
  value       = module.vpc.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "Production private subnet IDs."
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Production public subnet IDs."
  value       = module.vpc.public_subnet_ids
}

output "system_node_group_name" {
  description = "System managed node group name."
  value       = aws_eks_node_group.system.node_group_name
}

output "app_node_group_name" {
  description = "Application managed node group name."
  value       = aws_eks_node_group.app.node_group_name
}

output "application_irsa_role_arn" {
  description = "Application IRSA role ARN."
  value       = module.eks.application_irsa_role_arn
}

output "cert_manager_irsa_role_arn" {
  description = "cert-manager IRSA role ARN."
  value       = module.eks.cert_manager_irsa_role_arn
}

output "external_secrets_irsa_role_arn" {
  description = "External Secrets Operator IRSA role ARN."
  value       = module.eks.external_secrets_irsa_role_arn
}

output "cluster_autoscaler_irsa_role_arn" {
  description = "Cluster Autoscaler IRSA role ARN."
  value       = module.eks.cluster_autoscaler_irsa_role_arn
}

output "ebs_csi_irsa_role_arn" {
  description = "EBS CSI driver IRSA role ARN."
  value       = module.eks.ebs_csi_irsa_role_arn
}

output "efs_csi_role_arn" {
  description = "EFS CSI driver Pod Identity role ARN."
  value       = module.eks.efs_csi_role_arn
}

output "api_ecr_repository_url" {
  description = "API image ECR repository URL."
  value       = aws_ecr_repository.app["api"].repository_url
}

output "worker_ecr_repository_url" {
  description = "Worker image ECR repository URL."
  value       = aws_ecr_repository.app["worker"].repository_url
}

output "app_secret_name" {
  description = "Secrets Manager secret consumed by the xTRA app."
  value       = aws_secretsmanager_secret.app.name
}

output "rds_endpoint" {
  description = "PostgreSQL endpoint."
  value       = aws_db_instance.app.endpoint
}

output "efs_file_system_id" {
  description = "EFS file system ID for extraction files."
  value       = aws_efs_file_system.app.id
}
