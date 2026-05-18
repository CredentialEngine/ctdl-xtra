locals {
  github_repo    = "CredentialEngine/ctdl-xtra"
  aws_account_id = "996810415034"
}

# ---------------------------------------------------------------
# GitHub Actions OIDC
# ---------------------------------------------------------------

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

resource "aws_iam_role" "github_actions_ci" {
  name = "ctdl-xtra-github-actions-ci"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${local.github_repo}:*"
          }
        }
      }
    ]
  })
}

# ---------------------------------------------------------------
# ECR — push to STAGING repos, pull from STAGING to copy to PRODUCTION
# ---------------------------------------------------------------

resource "aws_iam_policy" "github_actions_ecr" {
  name = "ctdl-xtra-github-actions-ecr"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AuthToken"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "StagingReadWrite"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
        ]
        Resource = [
          "arn:aws:ecr:us-east-1:${local.aws_account_id}:repository/ctdl-xtra-staging/*",
        ]
      },
      {
        Sid    = "ProductionPromote"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:PutImage",
          "ecr:DescribeRepositories",
          "ecr:ListImages",
          "ecr:DescribeImages",
        ]
        Resource = [
          "arn:aws:ecr:us-east-1:${local.aws_account_id}:repository/ctdl-xtra/*",
        ]
      },
    ]
  })
}

# ---------------------------------------------------------------
# EKS — describe cluster so GitHub Actions can generate kubeconfig
# ---------------------------------------------------------------

resource "aws_iam_policy" "github_actions_eks" {
  name = "ctdl-xtra-github-actions-eks"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = "eks:DescribeCluster"
        Resource = [
          "arn:aws:eks:us-east-1:${local.aws_account_id}:cluster/ctdl-xtra-staging",
          "arn:aws:eks:us-east-1:${local.aws_account_id}:cluster/ctdl-xtra-prod",
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_ecr" {
  role       = aws_iam_role.github_actions_ci.name
  policy_arn = aws_iam_policy.github_actions_ecr.arn
}

resource "aws_iam_role_policy_attachment" "github_actions_eks" {
  role       = aws_iam_role.github_actions_ci.name
  policy_arn = aws_iam_policy.github_actions_eks.arn
}
