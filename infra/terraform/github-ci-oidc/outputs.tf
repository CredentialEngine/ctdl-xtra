output "github_actions_role_arn" {
  description = "IAM role ARN to set as AWS_ROLE_ARN secret in GitHub."
  value       = aws_iam_role.github_actions_ci.arn
}
