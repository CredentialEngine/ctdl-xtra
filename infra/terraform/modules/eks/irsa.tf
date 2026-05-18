locals {
  application_irsa_subjects = [
    for namespace in distinct(concat([var.app_namespace], var.additional_app_namespaces)) :
    "system:serviceaccount:${namespace}:${var.app_service_account}"
  ]

  application_s3_bucket_arns = [
    for bucket_name in var.application_s3_bucket_names :
    "arn:${data.aws_partition.current.partition}:s3:::${bucket_name}"
  ]

  external_secrets_secret_arns = [
    for prefix in var.external_secrets_secret_name_prefixes :
    "arn:${data.aws_partition.current.partition}:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${prefix}*"
  ]

  external_secrets_parameter_arns = [
    for prefix in var.external_secrets_ssm_parameter_prefixes :
    "arn:${data.aws_partition.current.partition}:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter/${trimprefix(prefix, "/")}*"
  ]
}

resource "aws_iam_role" "cert_manager" {
  name = "${var.cluster_name}-cert-manager-irsa-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.this.arn
        }
        Condition = {
          StringEquals = {
            "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
            "${local.oidc_provider_url}:sub" = "system:serviceaccount:cert-manager:cert-manager"
          }
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.cluster_name}-cert-manager-irsa-role"
  })
}

resource "aws_iam_policy" "cert_manager_route53" {
  name        = "${var.cluster_name}-cert-manager-route53-policy"
  description = "Permissions for cert-manager DNS01 validation in Route53"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "route53:GetChange",
          "route53:ChangeResourceRecordSets",
          "route53:ListResourceRecordSets"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:route53:::hostedzone/${var.route53_hosted_zone_id}",
          "arn:${data.aws_partition.current.partition}:route53:::change/*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = "route53:ListHostedZonesByName"
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cert_manager_route53" {
  policy_arn = aws_iam_policy.cert_manager_route53.arn
  role       = aws_iam_role.cert_manager.name
}

resource "aws_iam_role" "external_secrets" {
  name = "${var.cluster_name}-external-secrets-irsa-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.this.arn
        }
        Condition = {
          StringEquals = {
            "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
            "${local.oidc_provider_url}:sub" = "system:serviceaccount:external-secrets:external-secrets"
          }
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.cluster_name}-external-secrets-irsa-role"
  })
}

resource "aws_iam_policy" "external_secrets" {
  name        = "${var.cluster_name}-external-secrets-policy"
  description = "Permissions for External Secrets Operator to read scoped AWS secrets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      length(local.external_secrets_secret_arns) > 0 ? [
        {
          Sid = "ReadScopedSecrets"
          Action = [
            "secretsmanager:DescribeSecret",
            "secretsmanager:GetSecretValue"
          ]
          Effect   = "Allow"
          Resource = local.external_secrets_secret_arns
        }
      ] : [],
      length(local.external_secrets_parameter_arns) > 0 ? [
        {
          Sid = "ReadScopedParameters"
          Action = [
            "ssm:GetParameter",
            "ssm:GetParameters",
            "ssm:GetParametersByPath"
          ]
          Effect   = "Allow"
          Resource = local.external_secrets_parameter_arns
        }
      ] : [],
      [
        {
          Sid      = "DecryptSecretsWithAwsManagedKeys"
          Action   = "kms:Decrypt"
          Effect   = "Allow"
          Resource = "*"
          Condition = {
            StringEquals = {
              "kms:ViaService" = [
                "secretsmanager.${data.aws_region.current.name}.amazonaws.com",
                "ssm.${data.aws_region.current.name}.amazonaws.com"
              ]
            }
          }
        }
      ]
    )
  })
}

resource "aws_iam_role_policy_attachment" "external_secrets" {
  policy_arn = aws_iam_policy.external_secrets.arn
  role       = aws_iam_role.external_secrets.name
}

resource "aws_iam_role" "cluster_autoscaler" {
  name = "${var.cluster_name}-cluster-autoscaler-irsa-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.this.arn
        }
        Condition = {
          StringEquals = {
            "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
            "${local.oidc_provider_url}:sub" = "system:serviceaccount:kube-system:cluster-autoscaler"
          }
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = "${var.cluster_name}-cluster-autoscaler-irsa-role"
  })
}

resource "aws_iam_policy" "cluster_autoscaler" {
  name        = "${var.cluster_name}-cluster-autoscaler-policy"
  description = "Permissions for Cluster Autoscaler to manage tagged EKS node groups"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "DescribeAutoscaling"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "autoscaling:DescribeTags",
          "ec2:DescribeLaunchTemplateVersions",
          "eks:DescribeNodegroup"
        ]
        Effect   = "Allow"
        Resource = "*"
      },
      {
        Sid = "ScaleTaggedNodeGroups"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup"
        ]
        Effect   = "Allow"
        Resource = "*"
        Condition = {
          StringEquals = {
            "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/${var.cluster_name}" = "owned"
            "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/enabled"             = "true"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  policy_arn = aws_iam_policy.cluster_autoscaler.arn
  role       = aws_iam_role.cluster_autoscaler.name
}

resource "aws_iam_role" "application" {
  name = coalesce(var.application_irsa_role_name, "${var.cluster_name}-application-irsa-role")

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRoleWithWebIdentity"
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.this.arn
        }
        Condition = {
          StringEquals = {
            "${local.oidc_provider_url}:aud" = "sts.amazonaws.com"
            "${local.oidc_provider_url}:sub" = local.application_irsa_subjects
          }
        }
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name = coalesce(var.application_irsa_role_name, "${var.cluster_name}-application-irsa-role")
  })
}

resource "aws_iam_policy" "application_s3" {
  count = length(var.application_s3_bucket_names) > 0 ? 1 : 0

  name        = coalesce(var.application_irsa_policy_name, "${var.cluster_name}-application-s3-policy")
  description = "Scoped S3 permissions for ${var.cluster_name} workloads"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "S3ObjectRW"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject"
        ]
        Effect   = "Allow"
        Resource = [for bucket_arn in local.application_s3_bucket_arns : "${bucket_arn}/*"]
      },
      {
        Sid = "S3BucketReadMeta"
        Action = [
          "s3:GetBucketLocation",
          "s3:ListBucket"
        ]
        Effect   = "Allow"
        Resource = local.application_s3_bucket_arns
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "application_s3" {
  count = length(var.application_s3_bucket_names) > 0 ? 1 : 0

  policy_arn = aws_iam_policy.application_s3[0].arn
  role       = aws_iam_role.application.name
}
