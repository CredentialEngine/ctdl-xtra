variable "secret_name" {
  description = "Secrets Manager secret name."
  type        = string
}

variable "description" {
  description = "Secrets Manager secret description."
  type        = string
  default     = null
}

variable "secret_values" {
  description = "Initial JSON secret values. Values are ignored after creation."
  type        = map(string)
  sensitive   = true
}

variable "tags" {
  description = "Tags applied to the secret."
  type        = map(string)
  default     = {}
}
