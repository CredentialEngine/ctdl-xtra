variable "name" {
  description = "Name prefix for VPC resources."
  type        = string
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDR blocks."
  type        = list(string)
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDR blocks."
  type        = list(string)
}

variable "azs" {
  description = "Availability zones to spread subnets across."
  type        = list(string)
}

variable "single_nat_gateway" {
  description = "Use one shared NAT gateway instead of one NAT gateway per public subnet."
  type        = bool
  default     = false
}

variable "nat_eip_allocation_ids" {
  description = "Optional existing Elastic IP allocation IDs to use for NAT gateways instead of allocating new addresses."
  type        = list(string)
  default     = []
}

variable "common_tags" {
  description = "Tags applied to all supported resources."
  type        = map(string)
  default     = {}
}

variable "public_subnet_tags" {
  description = "Additional tags for public subnets."
  type        = map(string)
  default     = {}
}

variable "private_subnet_tags" {
  description = "Additional tags for private subnets."
  type        = map(string)
  default     = {}
}

variable "enable_flow_logs" {
  description = "Enable VPC flow logs to CloudWatch Logs."
  type        = bool
  default     = true
}

variable "flow_logs_retention_days" {
  description = "CloudWatch retention for VPC flow logs."
  type        = number
  default     = 30
}

variable "flow_logs_traffic_type" {
  description = "Traffic type captured by VPC flow logs. Valid values are ACCEPT, REJECT, or ALL."
  type        = string
  default     = "REJECT"

  validation {
    condition     = contains(["ACCEPT", "REJECT", "ALL"], var.flow_logs_traffic_type)
    error_message = "flow_logs_traffic_type must be ACCEPT, REJECT, or ALL."
  }
}
