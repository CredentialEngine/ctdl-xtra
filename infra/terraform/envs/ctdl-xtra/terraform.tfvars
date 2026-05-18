eks_cluster_name        = "cer-api-prod"
eks_nodegroup_role_name = "cer-api-prod-eks-nodegroup-role"

node_group_min_size     = 1
node_group_desired_size = 1
node_group_max_size     = 2
node_group_instance_types = [
  "m6i.large",
]
