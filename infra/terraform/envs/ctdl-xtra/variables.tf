variable "eks_cluster_name" {
  description = "Existing EKS cluster that will host CTDL xTRA."
  type        = string
}

variable "eks_nodegroup_role_name" {
  description = "Existing IAM role used by EKS managed node groups."
  type        = string
}

variable "node_group_min_size" {
  description = "Minimum size for the CTDL xTRA dedicated node group."
  type        = number
  default     = 1
}

variable "node_group_desired_size" {
  description = "Desired size for the CTDL xTRA dedicated node group."
  type        = number
  default     = 2
}

variable "node_group_max_size" {
  description = "Maximum size for the CTDL xTRA dedicated node group."
  type        = number
  default     = 4
}

variable "node_group_instance_types" {
  description = "Instance types for Puppeteer-capable CTDL xTRA nodes."
  type        = list(string)
  default     = ["m6i.large"]
}

variable "ctdl_xtra_secret_values" {
  description = "Initial app secret keys. Replace placeholders directly in Secrets Manager after creation."
  type        = map(string)
  sensitive   = true
  default = {
    AIRBRAKE_PROJECT_ID  = "CHANGE_ME"
    AIRBRAKE_PROJECT_KEY = "CHANGE_ME"
    COOKIE_KEY           = "CHANGE_ME"
    DATABASE_URL         = "CHANGE_ME"
    ENCRYPTION_KEY       = "CHANGE_ME"
    SMTP_PASSWORD        = "CHANGE_ME"
    SMTP_USER            = "CHANGE_ME"
  }
}
