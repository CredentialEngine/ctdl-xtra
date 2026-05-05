variable "name" {
  description = "Name tag for the EFS file system."
  type        = string
}

variable "vpc_id" {
  description = "VPC ID where EFS mount targets are created."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for EFS mount targets."
  type        = set(string)
}

variable "allowed_security_group_ids" {
  description = "Security groups allowed to mount EFS."
  type        = set(string)
}

variable "common_tags" {
  description = "Tags applied to EFS resources."
  type        = map(string)
  default     = {}
}
