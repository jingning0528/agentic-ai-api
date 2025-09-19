data "azurerm_virtual_network" "main" {
  name                = var.vnet_name
  resource_group_name = var.vnet_resource_group_name
}

# Reference existing subnets instead of creating new ones
data "azurerm_subnet" "privateendpoints" {
  name                 = var.private_endpoint_subnet_name
  virtual_network_name = var.vnet_name
  resource_group_name  = var.vnet_resource_group_name
}

data "azurerm_subnet" "web" {
  name                 = var.web_subnet_name
  virtual_network_name = var.vnet_name
  resource_group_name  = var.vnet_resource_group_name
}

data "azurerm_subnet" "container_instance" {
  name                 = var.container_instance_subnet_name
  virtual_network_name = var.vnet_name
  resource_group_name  = var.vnet_resource_group_name
}

# Note: Using existing subnets and their existing NSGs
# No new security groups or subnets are created in this module
# If you need specific NSG rules, they should be applied manually or through Azure CLI/Portal
