output "cluster_id" {
  description = "EKS cluster name/id."
  value       = aws_eks_cluster.this.id
}

output "cluster_arn" {
  description = "EKS cluster ARN."
  value       = aws_eks_cluster.this.arn
}

output "cluster_endpoint" {
  description = "EKS API endpoint."
  value       = aws_eks_cluster.this.endpoint
}

output "cluster_certificate_authority_data" {
  description = "Base64-encoded cluster CA data."
  value       = aws_eks_cluster.this.certificate_authority[0].data
  sensitive   = true
}

output "cluster_oidc_issuer_url" {
  description = "EKS OIDC issuer URL."
  value       = aws_eks_cluster.this.identity[0].oidc[0].issuer
}

output "cluster_primary_security_group_id" {
  description = "EKS cluster primary security group ID."
  value       = aws_eks_cluster.this.vpc_config[0].cluster_security_group_id
}

output "cluster_role_arn" {
  description = "EKS cluster IAM role ARN."
  value       = aws_iam_role.cluster.arn
}

output "nodegroup_role_arn" {
  description = "Managed node group IAM role ARN."
  value       = aws_iam_role.node_group.arn
}

output "nodegroup_role_name" {
  description = "Managed node group IAM role name."
  value       = aws_iam_role.node_group.name
}

output "oidc_provider_arn" {
  description = "EKS OIDC provider ARN."
  value       = aws_iam_openid_connect_provider.this.arn
}

output "application_irsa_role_arn" {
  description = "Application IRSA role ARN."
  value       = aws_iam_role.application.arn
}

output "cert_manager_irsa_role_arn" {
  description = "cert-manager IRSA role ARN."
  value       = aws_iam_role.cert_manager.arn
}

output "external_secrets_irsa_role_arn" {
  description = "External Secrets Operator IRSA role ARN."
  value       = aws_iam_role.external_secrets.arn
}

output "cluster_autoscaler_irsa_role_arn" {
  description = "Cluster Autoscaler IRSA role ARN."
  value       = aws_iam_role.cluster_autoscaler.arn
}

output "ebs_csi_irsa_role_arn" {
  description = "EBS CSI driver IRSA role ARN."
  value       = aws_iam_role.ebs_csi.arn
}

output "efs_csi_role_arn" {
  description = "EFS CSI driver Pod Identity role ARN, if enabled."
  value       = var.enable_efs_csi_driver ? aws_iam_role.efs_csi[0].arn : null
}
