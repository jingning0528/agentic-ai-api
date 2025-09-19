# -------------
# Root Level Terraform Configuration
# -------------
# Create the main resource group for all application resources
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.common_tags
  lifecycle {
    ignore_changes = [
      tags
    ]
  }
}

# -------------
# Modules based on Dependency
# -------------
module "network" {
  source = "./modules/network"

  common_tags              = var.common_tags
  resource_group_name      = azurerm_resource_group.main.name
  vnet_address_space       = var.vnet_address_space
  vnet_name                = var.vnet_name
  vnet_resource_group_name = var.vnet_resource_group_name

  depends_on = [azurerm_resource_group.main]
}

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.app_name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = var.log_analytics_sku
  retention_in_days   = var.log_analytics_retention_days
  tags                = var.common_tags
}

# Application Insights
resource "azurerm_application_insights" "main" {
  name                = "${var.app_name}-ai"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.main.id
  tags                = var.common_tags
}

module "cosmos" {
  source = "./modules/cosmos"

  app_name                   = var.app_name
  common_tags                = var.common_tags
  location                   = var.location
  resource_group_name        = azurerm_resource_group.main.name
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  embedding_dimensions       = 1536 # text-embedding-3-small dimensions

  depends_on = [azurerm_resource_group.main, module.network]
}

# Use container apps module instead of backend
module "container_apps" {
  source = "./modules/container-apps"

  app_name                    = var.app_name
  common_tags                 = var.common_tags
  location                    = var.location
  resource_group_name         = azurerm_resource_group.main.name
  log_analytics_workspace_id  = azurerm_log_analytics_workspace.main.id
  api_image                   = var.api_image
  app_env                     = var.app_env

  depends_on = [azurerm_resource_group.main, module.network]
}

# due to circular dependency issues this resource is created at root level
// Assign the App Service's managed identity to the Cosmos DB SQL Database with Data Contributor role

resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_role_assignment_app_service_data_contributor" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = module.cosmos.account_name
  role_definition_id  = "${module.cosmos.account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = module.container_apps.managed_identity_principal_id
  scope               = module.cosmos.account_id

  depends_on = [
    module.container_apps,
    module.cosmos
  ]
}