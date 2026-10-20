---
name: customer-quality
description: Operational runbook and automation skill for Customer Data Quality SaaS (UC-01) deployment, verification, acceptance testing, troubleshooting, rollback, and cleanup.
---

# Customer Data Quality Operations Skill

## Trigger
Use this skill when deploying, verifying, testing, troubleshooting, or tearing down the UC-01 Customer Data Quality SaaS application.

## Required Inputs & Environment
1. **Shell Requirement**: Use `bash` (Git Bash or WSL on Windows; standard bash on Linux/macOS). All deployment and verification scripts (`scripts/*`) are POSIX bash scripts.
2. **Azure Credentials**: Verified via `az login` prior to running cloud deployment commands.
3. **DATABASE_URL**: Neon PostgreSQL connection URL with psycopg3 driver (`postgresql+psycopg://...sslmode=require`).
4. **JWT_SECRET**: Secret key used to sign and verify HS256 JWT tokens.
5. **Environment Variables**:
   - `SUBSCRIPTION_STORE`: `file` (default) or `blob`
   - `ENABLE_TEST_HOOKS`: `true` to honour `X-Force-Failure` testing hook.

## Preflight Checklist
Before initiating any deployment or evaluation run, complete the following preflight checks:
```bash
# 1. Shell verification (must be bash)
echo "$BASH_VERSION"

# 2. Verify Python 3.11/3.12 and virtualenv
python --version
pip list | grep -E "fastapi|sqlalchemy|psycopg|alembic"

# 3. Verify Node & Frontend build
node -v
cd web && npm run build && cd ..

# 4. Verify Azure CLI login (only required for cloud deployments)
az account show

# 5. Verify Database connectivity
python scripts/test_db_connection.py
```

## Exact Script Commands and Expected Results

### 1. Bootstrap Cloud Resources
Creates Resource Group, Log Analytics workspace, Container Apps environment, Azure Container Registry (ACR), and Storage Account.
```bash
./scripts/bootstrap "rg-hackathon-dev" "southeastasia"
```
**Expected Result**:
- All Azure base resources provisioned with exit code 0.

### 2. Deploy Application
Builds Docker container image tagged with the current git commit SHA, runs Terraform targeting the Container App and private Blob container, runs Alembic migrations, and outputs the live HTTPS endpoint.
```bash
./scripts/deploy infra/dev.tfvars
```
**Expected Result**:
- Image built and pushed to ACR: `customer-saas:<git-sha>`.
- Terraform applies exactly two targeted resources (`azurerm_container_app.app` and `azurerm_storage_container.subscriptions`).
- Alembic runs `upgrade head` creating `runs` and `daily_usage` tables.
- Prints deployed app URL: `https://ca-customer-saas.<region>.azurecontainerapps.io`.

### 3. Verify Deployment
Executes live health checks, verifies zero-drift Terraform plan, and executes the acceptance suite:
```bash
./scripts/verify https://<app-fqdn> infra/dev.tfvars
```
**Expected Result**:
- `curl /health` returns HTTP 200 `{"status": "ok"}`.
- `terraform plan -detailed-exitcode` exits with code 0 (zero resource changes).
- All acceptance checks A02 through A11 pass green.

### 4. Harness Operations
Mint tokens or manage tenancy directly:
```bash
# Mint token for Pro Operator
python scripts/harness.py mint-token acme:Operator

# Mint token for Basic Viewer
python scripts/harness.py mint-token globex:Viewer

# Reset runs and daily quota
python scripts/harness.py reset-runs acme
python scripts/harness.py reset-quota acme

# Suspend and re-activate subscription
python scripts/harness.py suspend acme
python scripts/harness.py activate acme

# Switch plan
python scripts/harness.py set-plan acme Basic
```

## Stop Conditions
Halt immediately if:
- `scripts/test_db_connection.py` fails to connect to PostgreSQL.
- Database transaction in `accept_run` fails to acquire atomic lock or rolls back unexpectedly.
- Quota concurrency test in `test_service_db.py` produces flakiness.
- Any acceptance check from A02 to A11 fails status or response assertions.
- Non-zero exit code on `terraform plan -detailed-exitcode`.

## Troubleshooting & Forced Failure Hook

### Forced Failure Testing (A11)
To verify failure handling and quota debit persistence:
1. Ensure `ENABLE_TEST_HOOKS=true` is configured on the Container App environment.
2. Submit a run with the header:
   ```http
   POST /runs HTTP/1.1
   Authorization: Bearer <TOKEN>
   Idempotency-Key: test-forced-fail-001
   X-Force-Failure: true
   Content-Type: application/json

   { "operation": "process", "records": [...] }
   ```
3. **Expected Behavior**:
   - Status code is 201 Created.
   - Run status is persisted as `Failed` with error `{"code": "FORCED_FAILURE", "message": "Failure forced by test hook."}`.
   - Exactly 1 daily quota slot is debited.
   - Subsequent re-submissions with the same key return 200 OK replay with status `Failed` without re-running the processor.

### Common Issues
- **401 Unauthorized**: Missing or malformed Bearer token, or secret mismatch.
- **403 Forbidden**: Role is Viewer, tenant subscription is Suspended, or Basic plan attempted `process`.
- **404 Not Found**: Malformed UUID or cross-tenant query attempts.
- **409 Conflict**: Replay attempt with modified body payload or concurrent duplicate submission.
- **429 Quota Exhausted**: Daily quota of 3 (Basic) or 10 (Pro) reached.

## Rollback Procedure
If a regression is detected:
1. Identify the previous stable git commit SHA:
   ```bash
   PREV_SHA=$(git rev-parse --short HEAD~1)
   ```
2. Re-deploy specifying the prior image tag:
   ```bash
   cd infra
   terraform apply -auto-approve \
     -var-file="dev.tfvars" \
     -var="image_tag=${PREV_SHA}" \
     -target="azurerm_container_app.app" \
     -target="azurerm_storage_container.subscriptions"
   cd ..
   ```
3. Run verification:
   ```bash
   ./scripts/verify
   ```

## Teardown / Cleanup
To destroy only the two team-owned resources (`azurerm_container_app.app` and `azurerm_storage_container.subscriptions`):
```bash
./scripts/cleanup infra/dev.tfvars
```
**Confirmation**: Prompts for typed confirmation `DESTROY` to prevent accidental deletion.
