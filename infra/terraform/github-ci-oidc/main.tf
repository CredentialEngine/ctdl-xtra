terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  backend "s3" {
    bucket  = "terraform-state-o1r8"
    key     = "ctdl-xtra/github-ci-oidc/tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  description = "AWS region for provider operations."
  type        = string
  default     = "us-east-1"
}

variable "github_org" {
  description = "GitHub organization name."
  type        = string
  default     = "CredentialEngine"
}

variable "github_repo" {
  description = "GitHub repository name."
  type        = string
  default     = "ctdl-xtra"
}

variable "role_name" {
  description = "IAM role name for GitHub Actions OIDC."
  type        = string
  default     = "github-actions-ctdl-xtra"
}

variable "ecr_repository_names" {
  description = "ECR repositories this role can push to."
  type        = set(string)
  default = [
    "ctdl-xtra-app",
    "ctdl-xtra-worker",
  ]
}

variable "common_tags" {
  description = "Common tags for all resources."
  type        = map(string)
  default = {
    project = "ctdl-xtra"
  }
}

data "aws_caller_identity" "current" {}

data "aws_iam_openid_connect_provider" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_role" "github_actions" {
  name = var.role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = data.aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "ecr_push" {
  name = "ecr-push"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:PutImage"
        ]
        Resource = [
          for repository_name in var.ecr_repository_names :
          "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${repository_name}"
        ]
      }
      {
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster"
        ]
        Resource = "arn:aws:eks:${var.aws_region}:${data.aws_caller_identity.current.account_id}:cluster/cer-api-prod"
      }
    ]
  })
}

output "role_arn" {
  description = "IAM Role ARN for GitHub Actions. Store this as the AWS_ROLE_ARN repository secret."
  value       = aws_iam_role.github_actions.arn
}
