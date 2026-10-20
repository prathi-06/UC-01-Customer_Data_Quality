# A01 — Infrastructure Deployment (PENDING)

**Status**: PENDING — Azure deployment not yet completed.

## What Will Be Stored Here

Once the team runs `az login` and executes the deploy scripts, this folder will contain:

1. **terraform-validate.txt** — output of `terraform validate` (exit code 0).
2. **terraform-apply-summary.txt** — redacted summary of `terraform apply`, showing the two resources created (`azurerm_container_app.app` and `azurerm_storage_container.subscriptions`). All secrets redacted.
3. **health-response.json** — live `/health` response from the deployed Azure Container App URL confirming `{"status": "ok"}`.
4. **zero-drift-plan.txt** — output of `terraform plan -detailed-exitcode` run **after** apply, showing exit code 0 (no resource changes).

## Commands to Run (do not run until `az login` is complete)

```bash
# 1. Bootstrap base Azure resources (Resource Group, Container App Env, ACR, Storage Account)
./scripts/bootstrap "rg-customer-saas-dev" "southeastasia"

# 2. Deploy app (builds image, runs terraform apply, runs alembic upgrade head)
./scripts/deploy infra/dev.tfvars

# 3. Capture terraform validate output
cd infra && terraform validate > ../evidence/A01/terraform-validate.txt 2>&1

# 4. Verify live deployment
./scripts/verify https://<app-fqdn> infra/dev.tfvars

# 5. Capture zero-drift plan
cd infra && terraform plan -detailed-exitcode > ../evidence/A01/zero-drift-plan.txt 2>&1; echo "Exit code: $?" >> ../evidence/A01/zero-drift-plan.txt
```
