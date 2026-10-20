resource_group_name          = "rg-customer-saas-test"
location                     = "eastus"
container_app_environment_id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-customer-saas-test/providers/Microsoft.App/managedEnvironments/cae-customer-saas-test"
acr_login_server             = "acrcustomersaastest.azurecr.io"
image_name                   = "customer-saas"
storage_account_name         = "stcustomersaastest"
container_name               = "subscriptions"
enable_test_hooks            = false
