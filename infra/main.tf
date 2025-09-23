# -------------
# Root Level Terraform Configuration
# -------------
# Create the main resource group for all application resources

# resource "azurerm_resource_group" "main" {
#   name     = var.resource_group_name
#   location = var.location
#   tags     = var.common_tags
#   lifecycle {
#     ignore_changes = [
#       tags
#     ]
#   }
# }

# Data source to reference existing resource group if needed
data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

# Reference existing VNet
data "azurerm_virtual_network" "main" {
  name                = var.vnet_name
  resource_group_name = var.vnet_resource_group_name
}

# Web Subnet
resource "azapi_resource" "web_subnet" {
  name      = "web-subnet"
  type      = "Microsoft.Network/virtualNetworks/subnets@2023-04-01"
  parent_id = data.azurerm_virtual_network.main.id

  body = {
    properties = {
      addressPrefix = var.web_subnet_cidr
      networkSecurityGroup = { id = var.web_nsg_id }
    }
  }
}

# App Service Subnet
resource "azapi_resource" "app_service_subnet" {
  name      = "app-service-subnet"
  type      = "Microsoft.Network/virtualNetworks/subnets@2023-04-01"
  parent_id = data.azurerm_virtual_network.main.id

  body = {
    properties = {
      addressPrefix = var.app_service_subnet_cidr
      networkSecurityGroup = { id = var.as_nsg_id }
    }
  }
}

# Container Instance Subnet
resource "azapi_resource" "container_instance_subnet" {
  name      = "container-instance-subnet"
  type      = "Microsoft.Network/virtualNetworks/subnets@2023-04-01"
  parent_id = data.azurerm_virtual_network.main.id

  body = {
    properties = {
      addressPrefix = var.container_instance_subnet_cidr
      networkSecurityGroup = { id = var.ci_nsg_id }
    }
  }
}


# -------------
# Modules based on Dependency
# -------------
module "network" {
  source = "./modules/network"

  common_tags              = var.common_tags
  resource_group_name      = data.azurerm_resource_group.main.name
  vnet_address_space       = var.vnet_address_space
  vnet_name                = var.vnet_name
  vnet_resource_group_name = var.vnet_resource_group_name

  depends_on = [data.azurerm_resource_group.main]
}



module "backend" {
  source = "./modules/backend"

  api_image                               = var.api_image
  app_env                                 = var.app_env
  app_name                                = var.app_name
  app_service_sku_name_backend            = var.app_service_sku_name_backend
  app_service_subnet_id                   = module.network.app_service_subnet_id
  azure_openai_endpoint                   = var.azure_openai_endpoint
  azure_openai_api_key                    = var.azure_openai_api_key
  azure_openai_deployment_name            = var.azure_openai_deployment_name
  azure_openai_embedding_deployment       = var.azure_openai_embedding_deployment
  backend_subnet_id                       = module.network.app_service_subnet_id
  common_tags                             = var.common_tags
  frontend_possible_outbound_ip_addresses = ""
  location                                = var.location
  private_endpoint_subnet_id              = module.network.private_endpoint_subnet_id
  repo_name                               = var.repo_name
  resource_group_name                     = data.azurerm_resource_group.main.name
  image_tag                               = var.image_tag
  azure_openai_embedding_endpoint         = var.azure_openai_embedding_endpoint
  azure_openai_llm_endpoint               = var.azure_openai_llm_endpoint

}


