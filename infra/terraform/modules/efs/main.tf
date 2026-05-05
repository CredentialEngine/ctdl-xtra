resource "aws_security_group" "efs" {
  name        = "${var.name}-efs"
  description = "Allow NFS access to ${var.name}"
  vpc_id      = var.vpc_id

  tags = merge(var.common_tags, {
    Name = "${var.name}-efs"
  })
}

resource "aws_security_group_rule" "nfs" {
  for_each = var.allowed_security_group_ids

  type                     = "ingress"
  from_port                = 2049
  to_port                  = 2049
  protocol                 = "tcp"
  security_group_id        = aws_security_group.efs.id
  source_security_group_id = each.value
  description              = "Allow NFS from EKS worker nodes"
}

resource "aws_efs_file_system" "this" {
  creation_token   = var.name
  encrypted        = true
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"

  tags = merge(var.common_tags, {
    Name = var.name
  })
}

resource "aws_efs_mount_target" "this" {
  for_each = var.subnet_ids

  file_system_id  = aws_efs_file_system.this.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_access_point" "storage" {
  file_system_id = aws_efs_file_system.this.id

  posix_user {
    gid = 1000
    uid = 1000
  }

  root_directory {
    path = "/storage"

    creation_info {
      owner_gid   = 1000
      owner_uid   = 1000
      permissions = "0755"
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.name}-storage"
  })
}
