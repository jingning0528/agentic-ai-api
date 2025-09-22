output "appinsights_connection_string" { value = azurerm_application_insights.appinsights.connection_string }
output "appinsights_instrumentation_key" { value = azurerm_application_insights.appinsights.instrumentation_key }
output "log_analytics_workspace_id" { value = azurerm_log_analytics_workspace.workspace.id }
 
