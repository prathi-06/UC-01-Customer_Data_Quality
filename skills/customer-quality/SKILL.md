---
name: customer-quality
description: Operational runbook for deploying, verifying, testing, troubleshooting, rolling back, and cleaning up the UC-01 Customer Data Quality SaaS.
---

# Customer Data Quality Operations Runbook

## Trigger
Use this skill when deploying, verifying, testing, troubleshooting, rolling back, or cleaning up the UC-01 Customer Data Quality SaaS application.

## Required Inputs
Provide names only (never print or commit secret values):
- `APP_URL`
- `IMAGE_TAG`
- `DATABASE_URL`
- `JWT_SECRET`
- `SUBSCRIPTION_STORE`
- `ENABLE_TEST_HOOKS`
- `ACR_NAME`
- `AZURE_STORAGE_CONNECTION_STRING`
- `AZURE_STORAGE_CONTAINER_NAME`

## Preflight
Run the following preflight checks before proceeding. If any check fails, STOP immediately.
```bash
# 1. Verify Azure CLI login and active subscription
az account show

# 2. Verify Terraform is installed
terraform version

# 3. Verify Docker is installed and daemon is responsive
docker info

# 4. Verify local environment file exists
test -f .env || echo "MISSING .env"
```
STOP condition: If `az account show` fails, Terraform is missing, the Docker daemon is unreachable, or `.env` is absent, STOP and resolve before continuing.

## Deploy
Run the deployment script using the target variables file:
```bash
./scripts/deploy infra/dev.tfvars
```
Expected output:
- Container image built and pushed to ACR with tag matching `IMAGE_TAG` (`customer-saas:<git-sha>`).
- Terraform runs `init`, `validate`, and applies exactly two targeted resources (`azurerm_container_app.app` and `azurerm_storage_container.subscriptions`).
- Database migrations execute via `alembic upgrade head`.
- Script prints `=== DEPLOYMENT SUCCESSFUL ===` with `Deployed App URL: <APP_URL>`.

## Verify
Run the deployment verification script against the deployed app URL:
```bash
./scripts/verify "<APP_URL>" infra/dev.tfvars
```
Expected verification results:
- `GET /health` probe returns HTTP 200 with body `{"status": "ok"}`.
- Second `terraform plan -detailed-exitcode` exits with code 0 (zero resource drift).
- Validation on valid fixture (`fixtures/valid.json`) returns HTTP 201 with expected payload:
  - `valid_rows`: 2
  - `invalid_rows`: 0
  - `issues`: `[]`
- Validation on invalid fixture (`fixtures/invalid.json`) returns HTTP 201 with expected payload:
  - `valid_rows`: 2
  - `invalid_rows`: 4
  - Issues list containing exactly:
    - Rule R1 failure at `row_index: 3`, `field: "record_id"`
    - Rule R2 failure at `row_index: 4`, `field: "email"`
    - Rule R3 failure at `row_index: 5`, `field: "credit_limit"`
    - Rule R4 failure at `row_index: 6`, `field: "status"`
- Pro `process` operation on valid fixture returns HTTP 201 with expected payload:
  - Row 1: `record_id: "C01"`, `email: "alice@example.com"`, `contactable: true`
  - Row 2: `record_id: "C02"`, `email: "bob@example.com"`, `contactable: false`
  - Summary: `input_rows: 2`, `contactable_rows: 1`, `issues: []`

## Common Checks
To execute the automated acceptance test suite against a deployed environment:
```bash
python tests/acceptance.py --base-url "<APP_URL>"
```
Expected output and written evidence files:
- Executes checks A02 through A11 and writes sanitized JSON evidence files:
  - `evidence/A02.json`
  - `evidence/A03.json`
  - `evidence/A04.json`
  - `evidence/A05.json`
  - `evidence/A06.json`
  - `evidence/A07.json`
  - `evidence/A08.json`
  - `evidence/A09.json`
  - `evidence/A10.json`
  - `evidence/A11.json`

## Troubleshooting the Forced Failure
For forced-failure diagnostics (Check A11):
- Supply the header `X-Force-Failure: 1` or `X-Force-Failure: true` on `POST /runs`.
- Requirement: `ENABLE_TEST_HOOKS` must be `true` in the environment configuration. If false, the header is ignored and execution proceeds normally.
- Expected behavior:
  - Endpoint returns HTTP 201 Created.
  - Run status is recorded as `Failed` with error payload `PROCESSING_FAILED`.
  - Exactly one daily quota slot is debited for the tenant.
  - Replaying the same request with the identical `Idempotency-Key` returns HTTP 200 with the recorded `Failed` status and error without re-running the processor.

## Rollback
If a regression occurs, re-deploy using the prior git commit SHA image tag:
```bash
# 1. Identify previous stable commit SHA
PREV_SHA=$(git rev-parse --short HEAD~1)

# 2. Re-run deployment targeting the prior image tag
cd infra
terraform apply -auto-approve \
  -var-file="dev.tfvars" \
  -var="image_tag=${PREV_SHA}" \
  -target="azurerm_container_app.app" \
  -target="azurerm_storage_container.subscriptions"
cd ..

# 3. Re-run verification
./scripts/verify "<APP_URL>" infra/dev.tfvars
```
Expected output: Container App revisions roll back to image tag `${PREV_SHA}` and verification returns HTTP 200.

## Cleanup
To destroy only the two team-owned resources (`azurerm_container_app.app` and `azurerm_storage_container.subscriptions`):
```bash
./scripts/cleanup infra/dev.tfvars
```
- Destroys only the two team-owned resources.
- Requires explicit typed confirmation: user must enter `DESTROY`.
- **Assistant Rule**: The assistant must STOP and ask the human first before running `./scripts/cleanup`.

## Stop Conditions
Halt execution and report immediately if any of the following occur:
- Any command or script exits with a non-zero exit code.
- `terraform plan -detailed-exitcode` detects changes or exits with a non-zero exit code (non-empty second plan).
- Any HTTP request returns a `5xx` Server Error status code.
- Any cross-tenant data is observed or returned (such as non-404 status when querying another tenant's run).
