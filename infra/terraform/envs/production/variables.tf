# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------

variable "vpc_cidr" {
  description = "Production VPC CIDR block."
  type        = string
}

variable "public_subnet_cidrs" {
  description = "Production public subnet CIDR blocks."
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "Production private subnet CIDR blocks."
  type        = list(string)
}

variable "azs" {
  description = "Availability zones for the production cluster."
  type        = list(string)
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one NAT gateway per public subnet."
  type        = bool
  default     = false
}

variable "nat_eip_allocation_ids" {
  description = "Existing Elastic IP allocation IDs to use for NAT gateways."
  type        = list(string)
  default     = []
}

variable "enable_vpc_flow_logs" {
  description = "Enable VPC flow logs for production network visibility."
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------
# EKS
# ---------------------------------------------------------------------------

variable "cluster_version" {
  description = "Kubernetes version for the production EKS cluster."
  type        = string
}

variable "cluster_service_ipv4_cidr" {
  description = "Service IPv4 CIDR for the Kubernetes cluster."
  type        = string
  default     = null
}

variable "cluster_endpoint_private_access" {
  description = "Whether the private EKS API endpoint is enabled."
  type        = bool
  default     = true
}

variable "cluster_endpoint_public_access" {
  description = "Whether the public EKS API endpoint is enabled."
  type        = bool
  default     = true
}

variable "cluster_endpoint_public_access_cidrs" {
  description = "CIDR ranges allowed to access the public EKS API endpoint."
  type        = list(string)
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
  description = "Additional IAM principal ARNs to grant cluster admin access."
  type        = list(string)
  default     = []
}

variable "enable_cluster_secret_encryption" {
  description = "Encrypt Kubernetes secrets using a customer-managed KMS key."
  type        = bool
  default     = true
}

variable "route53_hosted_zone_id" {
  description = "Route53 hosted zone ID used by cert-manager DNS validation."
  type        = string
}

variable "enable_efs_csi_driver" {
  description = "Install the AWS EFS CSI driver add-on."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# IRSA
# ---------------------------------------------------------------------------

variable "app_namespace" {
  description = "Primary Kubernetes namespace for the xTRA workload."
  type        = string
  default     = "ctdl-xtra"
}

variable "additional_app_namespaces" {
  description = "Additional namespaces that may use the application IRSA role."
  type        = list(string)
  default     = []
}

variable "app_service_account" {
  description = "Kubernetes service account name for application IRSA."
  type        = string
  default     = "ctdl-xtra"
}

variable "application_s3_bucket_names" {
  description = "S3 buckets the xTRA service account can access."
  type        = list(string)
  default     = []
}

variable "external_secrets_secret_name_prefixes" {
  description = "Secrets Manager name prefixes readable by External Secrets Operator."
  type        = list(string)
  default     = ["ctdl-xtra/prod", "ctdl-xtra-prod"]
}

variable "external_secrets_ssm_parameter_prefixes" {
  description = "SSM Parameter Store prefixes readable by External Secrets Operator."
  type        = list(string)
  default     = ["ctdl-xtra/prod"]
}

# ---------------------------------------------------------------------------
# Application dependencies
# ---------------------------------------------------------------------------

variable "app_domain_name" {
  description = "Public hostname for the xTRA application."
  type        = string
  default     = "xtra.credentialengineregistry.org"
}

variable "app_secret_name" {
  description = "Secrets Manager JSON secret consumed by the xTRA workload."
  type        = string
  default     = "ctdl-xtra/prod/app"
}

variable "db_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "ctdl_xtra"
}

variable "db_username" {
  description = "PostgreSQL master username."
  type        = string
  default     = "ctdlxtra"
}

variable "db_engine_version" {
  description = "PostgreSQL engine version."
  type        = string
  default     = "17.5"
}

variable "db_instance_class" {
  description = "PostgreSQL instance class."
  type        = string
  default     = "db.t4g.small"
}

variable "db_allocated_storage" {
  description = "Initial PostgreSQL storage in GiB."
  type        = number
  default     = 50
}

variable "db_max_allocated_storage" {
  description = "Maximum PostgreSQL autoscaled storage in GiB."
  type        = number
  default     = 200
}

variable "db_multi_az" {
  description = "Enable Multi-AZ standby for PostgreSQL."
  type        = bool
  default     = true
}

variable "db_backup_retention_days" {
  description = "PostgreSQL backup retention in days."
  type        = number
  default     = 14
}

# ---------------------------------------------------------------------------
# Node groups
# ---------------------------------------------------------------------------

variable "system_node_instance_types" {
  description = "Instance types for untainted system nodes."
  type        = list(string)
  default     = ["t3.medium"]
}

variable "system_node_disk_size" {
  description = "Disk size in GiB for system nodes."
  type        = number
  default     = 30
}

variable "system_node_min_size" {
  description = "Minimum system node count."
  type        = number
  default     = 2
}

variable "system_node_max_size" {
  description = "Maximum system node count."
  type        = number
  default     = 4
}

variable "system_node_desired_size" {
  description = "Desired system node count."
  type        = number
  default     = 2
}

variable "app_node_instance_types" {
  description = "Instance types for xTRA workload nodes."
  type        = list(string)
  default     = ["m7i.large"]
}

variable "app_node_disk_size" {
  description = "Disk size in GiB for xTRA workload nodes."
  type        = number
  default     = 50
}

variable "app_node_min_size" {
  description = "Minimum xTRA workload node count."
  type        = number
  default     = 2
}

variable "app_node_max_size" {
  description = "Maximum xTRA workload node count."
  type        = number
  default     = 8
}

variable "app_node_desired_size" {
  description = "Desired xTRA workload node count."
  type        = number
  default     = 2
}
