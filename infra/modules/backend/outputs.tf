output "backend_managed_identity_principal_id" {
  description = "The principal ID of the API's managed identity to assign roles in Cosmos DB."
  value       = azurerm_linux_web_app.backend.identity[0].principal_id
  depends_on  = [azurerm_linux_web_app.backend]
}

output "cosmosdb_primary_key" {
  description = "Primary key for the Cosmos DB account"
  value       = azurerm_cosmosdb_account.cosmosdb_sql.primary_master_key
  sensitive   = true
}

