variable "cluster_name" {
  description = "EKS cluster name."
  type        = string
}

variable "cluster_version" {
  description = "Kubernetes minor version for the EKS cluster."
  type        = string
}

variable "cluster_service_ipv4_cidr" {
  description = "Service IPv4 CIDR for the Kubernetes cluster."
  type        = string
  default     = null
}

variable "cluster_endpoint_private_access" {
  description = "Enable private EKS API endpoint access."
  type        = bool
  default     = true
}

variable "cluster_endpoint_public_access" {
  description = "Enable public EKS API endpoint access."
  type        = bool
  default     = true
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDRs allowed to access the public EKS API endpoint."
  type        = list(string)
  default     = []
}

variable "authentication_mode" {
  description = "EKS authentication mode."
  type        = string
  default     = "API_AND_CONFIG_MAP"
}

variable "bootstrap_cluster_creator_admin_permissions" {
  description = "Grant the cluster creator admin permissions at bootstrap."
  type        = bool
  default     = true
}

variable "cluster_admin_principal_arns" {
  description = "Additional IAM principal ARNs to grant EKS cluster admin access."
  type        = list(string)
  default     = []
}

variable "enable_cluster_secret_encryption" {
  description = "Encrypt Kubernetes secrets using a customer-managed KMS key."
  type        = bool
  default     = true
}

variable "cluster_kms_deletion_window_days" {
  description = "Deletion window in days for the EKS secrets KMS key."
  type        = number
  default     = 30
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for EKS control plane and nodes."
  type        = list(string)
}

variable "common_tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}

variable "eks_oidc_root_ca_thumbprint" {
  description = "Root CA thumbprint for the EKS OIDC provider."
  type        = string
  default     = "9e99a48a9960b14926bb7f3b02e22da2b0ab7280"
}

variable "route53_hosted_zone_id" {
  description = "Route53 hosted zone ID used by cert-manager DNS validation."
  type        = string
}

variable "app_namespace" {
  description = "Primary Kubernetes namespace for the application service account."
  type        = string
}

variable "additional_app_namespaces" {
  description = "Additional namespaces that may use the application IRSA role."
  type        = list(string)
  default     = []
}

variable "app_service_account" {
  description = "Kubernetes service account name for application IRSA."
  type        = string
}

variable "application_irsa_role_name" {
  description = "Optional application IRSA role name override."
  type        = string
  default     = null
}

variable "application_irsa_policy_name" {
  description = "Optional application IAM policy name override."
  type        = string
  default     = null
}

variable "application_s3_bucket_names" {
  description = "S3 buckets the application service account can access."
  type        = list(string)
  default     = []
}

variable "external_secrets_secret_name_prefixes" {
  description = "Secrets Manager name prefixes readable by External Secrets Operator."
  type        = list(string)
  default     = []
}

variable "external_secrets_ssm_parameter_prefixes" {
  description = "SSM Parameter Store prefixes readable by External Secrets Operator."
  type        = list(string)
  default     = []
}

variable "enable_efs_csi_driver" {
  description = "Install the AWS EFS CSI driver add-on."
  type        = bool
  default     = false
}
