output "RESOURCE_GROUP_ID" {
  value = data.azurerm_resource_group.main.id
}

output "AZURE_CONTAINER_REGISTRY_ENDPOINT" {
  value = azurerm_container_registry.main.login_server
}

output "CONTAINER_APP_FQDN" {
  value = azurerm_container_app.api.latest_revision_fqdn
}

output "CONTAINER_APP_NAME" {
  value = azurerm_container_app.api.name
}