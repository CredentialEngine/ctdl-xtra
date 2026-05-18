output "repository_urls" {
  description = "Repository URLs keyed by repository name."
  value       = { for name, repo in aws_ecr_repository.this : name => repo.repository_url }
}
