vpc_cidr             = "10.41.0.0/16"
public_subnet_cidrs  = ["10.41.1.0/24", "10.41.2.0/24"]
private_subnet_cidrs = ["10.41.11.0/24", "10.41.12.0/24"]
azs                  = ["us-east-1a", "us-east-1b"]

single_nat_gateway     = true
enable_vpc_flow_logs   = true
nat_eip_allocation_ids = []

cluster_version = "1.35"

cluster_endpoint_private_access      = true
cluster_endpoint_public_access       = true
cluster_endpoint_public_access_cidrs = ["0.0.0.0/0"]

authentication_mode                         = "API_AND_CONFIG_MAP"
bootstrap_cluster_creator_admin_permissions = true
cluster_admin_principal_arns                = ["arn:aws:iam::996810415034:role/ctdl-xtra-github-actions-ci"]

route53_hosted_zone_id           = "Z1N75467P1FUL5"
enable_cluster_secret_encryption = true
enable_efs_csi_driver            = true

app_namespace       = "ctdl-xtra"
app_service_account = "ctdl-xtra"

external_secrets_secret_name_prefixes = [
  "ctdl-xtra/staging",
  "ctdl-xtra-staging"
]

external_secrets_ssm_parameter_prefixes = [
  "ctdl-xtra/staging"
]

app_domain_name = "xtra-staging.credentialengineregistry.org"
app_secret_name = "ctdl-xtra/staging/app"

db_name                  = "ctdl_xtra"
db_username              = "ctdlxtra"
db_engine_version        = "17.5"
db_instance_class        = "db.t4g.small"
db_allocated_storage     = 20
db_max_allocated_storage = 100
db_multi_az              = false
db_backup_retention_days = 7

system_node_instance_types = ["t3.medium"]
system_node_min_size       = 1
system_node_max_size       = 3
system_node_desired_size   = 1
system_node_disk_size      = 20

app_node_instance_types = ["t3.large"]
app_node_min_size       = 1
app_node_max_size       = 4
app_node_desired_size   = 1
app_node_disk_size      = 30
