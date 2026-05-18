output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}

output "vpc_cidr_block" {
  description = "VPC CIDR block."
  value       = aws_vpc.main.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs."
  value       = aws_subnet.private[*].id
}

output "nat_gateway_ids" {
  description = "NAT gateway IDs."
  value       = aws_nat_gateway.main[*].id
}
