# Reference existing subnet CIDRs based on your Azure environment
locals {
  # Use the actual subnet CIDRs from your existing infrastructure
  app_service_subnet_cidr        = "10.46.90.32/27"  # web-subnet
  web_subnet_cidr                = "10.46.90.32/27"  # web-subnet (same as app service for Container Apps)
  private_endpoints_subnet_cidr  = "10.46.90.64/28"  # privateendpoints-subnet
  container_instance_subnet_cidr = "10.46.90.80/28"  # container-instance-subnet
  aks_nodes_subnet_cidr          = "10.46.90.0/27"   # aks-nodes (for reference)
}
