variable "resource_group_name" {
  type        = string
  description = "Resource group name"
  default     = "rg-customer-saas-dev"
}

variable "location" {
  type        = string
  description = "Azure region"
  default     = "eastus"
}

variable "container_app_environment_id" {
  type        = string
  description = "Container App Environment Resource ID"
}

variable "acr_login_server" {
  type        = string
  description = "ACR login server (e.g. myacr.azurecr.io)"
}

variable "app_name" {
  type        = string
  description = "Container App resource name"
  default     = "ca-customer-saas"
}

variable "image_name" {
  type        = string
  description = "Container image name"
  default     = "customer-saas"
}

variable "image_tag" {
  type        = string
  description = "Container image git SHA tag (never latest, never timestamp)"
  default     = "git-sha-manual"
}

variable "database_url" {
  type        = string
  sensitive   = true
  description = "PostgreSQL connection string with psycopg driver and sslmode=require (passed via TF_VAR_database_url)"
}

variable "jwt_secret" {
  type        = string
  sensitive   = true
  description = "JWT Secret for session tokens (passed via TF_VAR_jwt_secret)"
}

variable "storage_account_name" {
  type        = string
  description = "Storage account name for private blob storage"
}

variable "container_name" {
  type        = string
  description = "Name of private blob container"
  default     = "subscriptions"
}

variable "enable_test_hooks" {
  type        = bool
  description = "Test-only switch to enable post-acceptance forced failure hook (dev only, false in test/prod)"
  default     = false
}
