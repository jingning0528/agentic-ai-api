# -------------
# Root Level Terraform Configuration
# -------------
# Create new resource group in Canada Central
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.common_tags
}

# Log Analytics Workspace - Deploy in Canada Central for VNET integration
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.app_name}-logs"
  location            = var.location  # Canada Central - where VNET is
  resource_group_name = azurerm_resource_group.main.name
  sku                 = var.log_analytics_sku
  retention_in_days   = var.log_analytics_retention_days
  tags                = var.common_tags
}

# Application Insights - Deploy in Canada Central
resource "azurerm_application_insights" "main" {
  name                = "${var.app_name}-ai"
  location            = var.location  # Canada Central - where VNET is
  resource_group_name = azurerm_resource_group.main.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.main.id
  tags                = var.common_tags
}

# -------------
# Modules based on Dependency
# -------------
module "network" {
  source = "./modules/network"

  common_tags              = var.common_tags
  location                 = var.location  # Canada Central - where VNET is
  resource_group_name      = azurerm_resource_group.main.name
  vnet_address_space       = var.vnet_address_space
  vnet_name                = var.vnet_name
  vnet_resource_group_name = var.vnet_resource_group_name

  depends_on = [azurerm_resource_group.main]
}

module "cosmos" {
  source = "./modules/cosmos"

  app_name                   = var.app_name
  common_tags                = var.common_tags
  location                   = var.location  # Canada Central - where VNET is
  resource_group_name        = azurerm_resource_group.main.name
  private_endpoint_subnet_id = module.network.private_endpoint_subnet_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  embedding_dimensions       = 1536 # text-embedding-3-small dimensions

  depends_on = [azurerm_resource_group.main, module.network]
}

# Container Registry - Deploy in Canada Central for better performance
resource "azurerm_container_registry" "main" {
  name                = "${var.app_name}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location  # Canada Central - where VNET is
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.common_tags
}

# Container App Environment - Deploy in Canada Central for VNET integration
resource "azurerm_container_app_environment" "main" {
  name                         = "${var.app_name}-env"
  location                     = var.location  # Canada Central - where VNET is
  resource_group_name          = azurerm_resource_group.main.name
  log_analytics_workspace_id   = azurerm_log_analytics_workspace.main.id
  internal_load_balancer_enabled = true  # Disable public IP addresses due to policy
  tags                         = var.common_tags
}

# User-assigned Managed Identity - Deploy in Canada Central
resource "azurerm_user_assigned_identity" "main" {
  name                = "${var.app_name}-identity"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location  # Canada Central - where VNET is
  tags                = var.common_tags
}

# Container App - Deploy in Canada Central for VNET integration
resource "azurerm_container_app" "api" {
  name                         = "${var.app_name}-api"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = var.common_tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.main.id]
  }

  template {
    container {
      name   = "api"
      image  = var.api_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        value = azurerm_application_insights.main.connection_string
      }
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    traffic_weight {
      percentage      = 100
      latest_revision = true
    }
  }
}

# due to circular dependency issues this resource is created at root level
// Assign the App Service's managed identity to the Cosmos DB SQL Database with Data Contributor role
resource "azurerm_cosmosdb_sql_role_assignment" "cosmosdb_role_assignment_app_service_data_contributor" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = module.cosmos.account_name
  role_definition_id  = "${module.cosmos.account_id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.main.principal_id
  scope               = module.cosmos.account_id

  depends_on = [
    azurerm_user_assigned_identity.main,
    module.cosmos
  ]
}
