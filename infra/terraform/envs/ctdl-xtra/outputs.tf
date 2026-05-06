output "ecr_repository_urls" {
  description = "CTDL xTRA ECR repository URLs."
  value       = module.ecr.repository_urls
}

output "secret_name" {
  description = "Secrets Manager secret backing the ExternalSecret."
  value       = module.ctdl_xtra_secret.secret_name
}

output "efs_file_system_id" {
  description = "EFS file system ID for extraction storage."
  value       = module.efs.file_system_id
}

output "efs_storage_access_point_id" {
  description = "EFS access point ID for /app/storage."
  value       = module.efs.storage_access_point_id
}
