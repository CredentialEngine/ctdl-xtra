output "file_system_id" {
  description = "EFS file system ID."
  value       = aws_efs_file_system.this.id
}

output "storage_access_point_id" {
  description = "EFS access point ID for extraction storage."
  value       = aws_efs_access_point.storage.id
}
