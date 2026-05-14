locals {
  app_secret_values = {
    DATABASE_URL          = "postgresql://${var.db_username}:${random_password.db_password.result}@${aws_db_instance.app.address}:${aws_db_instance.app.port}/${var.db_name}?sslmode=require"
    REDIS_URL             = "rediss://:${random_password.redis_auth_token.result}@${aws_elasticache_replication_group.app.primary_endpoint_address}:6379"
    ENCRYPTION_KEY        = random_password.encryption_key.result
    COOKIE_KEY            = random_id.cookie_key.hex
    EXTRACTION_FILES_PATH = "/data/extractions"
    CLIENT_PATH           = "/app/public"
    FRONTEND_URL          = "https://${var.app_domain_name}"
    NODE_ENV              = "production"
    PORT                  = "3000"
  }
}

# ---------------------------------------------------------------
# Container Images
# ---------------------------------------------------------------

resource "aws_ecr_repository" "app" {
  for_each = toset(["api", "worker"])

  name                 = "${local.project_name}/${each.key}"
  image_tag_mutability = "MUTABLE"

  encryption_configuration {
    encryption_type = "AES256"
  }

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = merge(local.common_tags, {
    Name = "${local.project_name}-${each.key}"
  })
}

resource "aws_ecr_lifecycle_policy" "app" {
  for_each = aws_ecr_repository.app

  repository = each.value.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep the last 50 production images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["prod-", "latest"]
          countType     = "imageCountMoreThan"
          countNumber   = 50
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ---------------------------------------------------------------
# Database
# ---------------------------------------------------------------

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "app" {
  name       = "${local.cluster_name}-db"
  subnet_ids = module.vpc.private_subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-db"
  })
}

resource "aws_security_group" "rds" {
  name        = "${local.cluster_name}-rds"
  description = "Allow PostgreSQL access from the ${local.cluster_name} VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "PostgreSQL from private workloads"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-rds"
  })
}

resource "aws_db_parameter_group" "app" {
  name   = "${local.cluster_name}-postgres${replace(var.db_engine_version, ".", "")}"
  family = "postgres${split(".", var.db_engine_version)[0]}"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-postgres"
  })
}

resource "aws_db_instance" "app" {
  identifier = "${local.cluster_name}-postgres"

  engine         = "postgres"
  engine_version = var.db_engine_version
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = random_password.db_password.result

  db_subnet_group_name   = aws_db_subnet_group.app.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.app.name
  publicly_accessible    = false
  multi_az               = var.db_multi_az

  backup_retention_period = var.db_backup_retention_days
  backup_window           = "07:00-08:00"
  maintenance_window      = "sun:08:00-sun:09:00"
  copy_tags_to_snapshot   = true

  auto_minor_version_upgrade   = true
  deletion_protection          = true
  final_snapshot_identifier    = "${local.cluster_name}-postgres-final"
  performance_insights_enabled = true
  skip_final_snapshot          = false

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-postgres"
  })
}

# ---------------------------------------------------------------
# Redis
# ---------------------------------------------------------------

resource "random_password" "redis_auth_token" {
  length  = 32
  special = false
}

resource "aws_elasticache_subnet_group" "app" {
  name       = "${local.cluster_name}-redis"
  subnet_ids = module.vpc.private_subnet_ids

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis"
  })
}

resource "aws_security_group" "redis" {
  name        = "${local.cluster_name}-redis"
  description = "Allow Redis access from the ${local.cluster_name} VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "Redis from private workloads"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis"
  })
}

resource "aws_elasticache_parameter_group" "app" {
  name   = "${local.cluster_name}-redis7"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis7"
  })
}

resource "aws_elasticache_replication_group" "app" {
  replication_group_id = local.cluster_name
  description          = "Redis for ${local.cluster_name}"

  engine               = "redis"
  engine_version       = var.redis_engine_version
  node_type            = var.redis_node_type
  port                 = 6379
  parameter_group_name = aws_elasticache_parameter_group.app.name

  subnet_group_name  = aws_elasticache_subnet_group.app.name
  security_group_ids = [aws_security_group.redis.id]

  num_cache_clusters         = 2
  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.redis_auth_token.result

  snapshot_retention_limit = var.redis_snapshot_retention_days
  snapshot_window          = "06:00-07:00"
  maintenance_window       = "sun:07:00-sun:08:00"
  apply_immediately        = false

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-redis"
  })
}

# ---------------------------------------------------------------
# Shared Extraction Files
# ---------------------------------------------------------------

resource "aws_security_group" "efs" {
  name        = "${local.cluster_name}-efs"
  description = "Allow NFS access from the ${local.cluster_name} VPC"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "NFS from private workloads"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-efs"
  })
}

resource "aws_efs_file_system" "app" {
  creation_token = "${local.cluster_name}-files"
  encrypted      = true

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = merge(local.common_tags, {
    Name = "${local.cluster_name}-files"
  })
}

resource "aws_efs_backup_policy" "app" {
  file_system_id = aws_efs_file_system.app.id

  backup_policy {
    status = "ENABLED"
  }
}

resource "aws_efs_mount_target" "app" {
  for_each = toset(module.vpc.private_subnet_ids)

  file_system_id  = aws_efs_file_system.app.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}

# ---------------------------------------------------------------
# Runtime Secret
# ---------------------------------------------------------------

resource "random_password" "encryption_key" {
  length  = 32
  special = false
}

resource "random_id" "cookie_key" {
  byte_length = 32
}

resource "aws_secretsmanager_secret" "app" {
  name        = var.app_secret_name
  description = "Runtime configuration for ${local.cluster_name}"

  tags = merge(local.common_tags, {
    Name = var.app_secret_name
  })
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id     = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(local.app_secret_values)
}
