
output "container_instance_subnet_id" {
  description = "The subnet ID for the container instance."
  value       = data.azurerm_subnet.container_instance.id
}

output "app_service_subnet_id" {
  description = "The subnet ID for the App Service/Container Apps."
  value       = data.azurerm_subnet.web.id
}

output "private_endpoint_subnet_id" {
  description = "The subnet ID for private endpoints."
  value       = data.azurerm_subnet.privateendpoints.id
}

output "web_subnet_id" {
  description = "The subnet ID for web/Container Apps."
  value       = data.azurerm_subnet.web.id
}

output "dns_servers" {
  description = "The DNS servers for the virtual network."
  value       = data.azurerm_virtual_network.main.dns_servers
}