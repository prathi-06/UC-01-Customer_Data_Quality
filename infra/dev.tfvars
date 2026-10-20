resource_group_name          = "rg-customer-saas-dev"
location                     = "eastus"
container_app_environment_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-customer-saas-dev/providers/Microsoft.App/managedEnvironments/cae-customer-saas-dev"
acr_login_server             = "acrcustomersaasdev.azurecr.io"
image_name                   = "customer-saas"
storage_account_name         = "stcustomersaasdev"
container_name               = "subscriptions"
enable_test_hooks            = true
