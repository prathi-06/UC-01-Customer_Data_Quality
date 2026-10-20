terraform {
  required_version = ">= 1.5.0, < 2.0.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# RESOURCE 1: Private Azure Blob Container for subscriptions
resource "azurerm_storage_container" "subscriptions" {
  name                  = var.container_name
  storage_account_name  = var.storage_account_name
  container_access_type = "private"
}

# RESOURCE 2: Azure Container App with external ingress and probes
resource "azurerm_container_app" "app" {
  name                         = var.app_name
  container_app_environment_id = var.container_app_environment_id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"

  secret {
    name  = "database-url"
    value = var.database_url
  }

  secret {
    name  = "jwt-secret"
    value = var.jwt_secret
  }

  template {
    min_replicas = 1
    max_replicas = 3

    container {
      name   = "customer-saas-app"
      image  = "${var.acr_login_server}/${var.image_name}:${var.image_tag}"
      cpu    = 0.5
      memory = "1.0Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }

      env {
        name        = "JWT_SECRET"
        secret_name = "jwt-secret"
      }

      env {
        name  = "SUBSCRIPTION_STORE"
        value = "blob"
      }

      env {
        name  = "ENABLE_TEST_HOOKS"
        value = tostring(var.enable_test_hooks)
      }

      liveness_probe {
        path                    = "/health"
        port                    = 8000
        transport               = "HTTP"
        initial_delay           = 5
        interval_seconds        = 10
        timeout                 = 3
        failure_count_threshold = 3
      }

      readiness_probe {
        path                    = "/health"
        port                    = 8000
        transport               = "HTTP"
        interval_seconds        = 10
        timeout                 = 3
        failure_count_threshold = 3
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

output "app_fqdn" {
  value       = azurerm_container_app.app.latest_revision_fqdn
  description = "The deployed Container App FQDN"
}

output "app_url" {
  value       = "https://${azurerm_container_app.app.latest_revision_fqdn}"
  description = "The deployed Container App base URL"
}
