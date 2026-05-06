variable "repository_names" {
  description = "ECR repository names to create."
  type        = set(string)
}

variable "common_tags" {
  description = "Tags applied to all repositories."
  type        = map(string)
  default     = {}
}
