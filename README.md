# UC-01 Customer Data Quality SaaS

A subscription-based Customer Data Quality SaaS built for the Advantix final round.

---

## 1. System Architecture

```mermaid
flowchart TD
    Client["Browser UI or API Client"] -->|"HTTP Requests"| FastAPI["FastAPI Application in app/main.py"]
    FastAPI -->|"StaticFiles Mount"| Frontend["React and TypeScript UI in web/dist"]
    FastAPI -->|"API Router, 6 routes"| Routes["API Routes in app/routes.py"]

    subgraph Pipeline["Request Pipeline for POST /runs"]
        Routes -->|"1. Verify Token"| Auth["Auth Guard in app/auth.py"]
        Routes -->|"2. Check Tenant Override"| OverrideGuard["Override Guard in app/auth.py"]
        Routes -->|"3. Validate Body and Bounds"| BodyValidator["Raw Body Parser in app/routes.py"]
        Routes -->|"4. Plan Entitlement"| PlanGuard["require_plan_entitlement in app/routes.py"]
        Routes -->|"5. Atomic Accept and Quota"| ServiceTx["Single Transaction in app/service.py"]
        Routes -->|"6. Engine Execution"| Logic["Validation and Processor in app/validation.py and processor.py"]
    end

    ServiceTx -->|"SQLAlchemy 2.0 Core and psycopg 3"| NeonDB[("Neon PostgreSQL 18: runs and daily_usage")]
    Routes -->|"Subscription Store"| SubStore["Subscription Store: File or Azure Blob"]
```

---

## 2. Deviations from the brief

**Database: PostgreSQL 18 on Neon (Singapore), not Azure SQL.**
We chose PostgreSQL because we could set it up in minutes on a free plan with no card, and it runs the same way in Docker for local testing. It supports everything the design needs: a unique constraint on (tenant, key) and a conditional upsert for the daily quota, so the claim and the debit stay atomic in one transaction (section 4). The same idea works on Azure SQL (insert and catch duplicate-key errors 2627 or 2601, then UPDATE ... WHERE AcceptedRuns < limit and check @@ROWCOUNT). That version is described in section 4 but we did not implement or test it. Organiser confirmation that PostgreSQL is acceptable: PENDING.

**Environment.** We set up our own Azure environment. scripts/bootstrap creates the resource group, Log Analytics workspace, Container Apps environment, registry and storage account with the az CLI, so Terraform manages exactly the two resources the brief names.

**Sessions.** There is no login route, because the brief fixes the app at six routes. scripts/harness.py mints signed session tokens and the app verifies them on every protected route. Tenant and role come only from that token.

**Request handling.** The API reads the raw body and validates it by hand, so malformed, oversized or wrong-shaped input returns 400. FastAPI's default validation would return 422.

**Frontend.** The React UI is built into the same container and served by FastAPI, so there is one origin and no CORS.

**Test hook.** ENABLE_TEST_HOOKS switches on the forced-failure hook (X-Force-Failure) for check A11. It is true on the dev deployment and false otherwise.

**Out of scope per the brief:** queues, remote ERP calls, payment checkout, signup, approval workflows, schedulers and extra admin screens.
**Our own scoping choices:** JSON input only (no CSV), no password store, no CI/CD pipeline.

---

## 3. Database Schema & DDL Notes

### Tables
1. **`runs`**:
   - `run_id` (UUID, Primary Key)
   - `tenant_id` (VARCHAR(64), Indexed)
   - `idempotency_key` (VARCHAR(128))
   - `input_fingerprint` (CHAR(64) SHA-256)
   - `operation` (VARCHAR(32))
   - `status` (VARCHAR(32): `Running`, `Succeeded`, `Failed`)
   - `request_json` (JSONB)
   - `result_json` (JSONB)
   - `error_message` (TEXT)
   - `submitted_by` (VARCHAR(64))
   - `created_at` (TIMESTAMP WITH TIME ZONE, Default UTC)
   - `finished_at` (TIMESTAMP WITH TIME ZONE)
   - `completed_at` (TIMESTAMP WITH TIME ZONE)
   - Unique Constraint: `(tenant_id, idempotency_key)`

2. **`daily_usage`**:
   - `tenant_id` (VARCHAR(64))
   - `usage_date_utc` (DATE)
   - `accepted_runs` (INTEGER, Default 0)
   - Primary Key: `(tenant_id, usage_date_utc)`

> **Schema Clarification (`finished_at` vs `completed_at`)**:
> Migration `0001_initial_schema.py` created `finished_at`. Migration `0002_add_completed_at.py` introduced `completed_at` for spec alignment. All application queries write to both or preserve `finished_at` for complete backwards compatibility.

---

## 4. Atomic Execution Pattern & Check Order Pipeline

### Atomic Single-Transaction Claim and Debit (PostgreSQL Implementation)
The acceptance of any submission and quota debit runs as a single database transaction in `accept_run()`:

1. **Speculative Claim of Idempotency Key**:
   ```sql
   INSERT INTO runs (run_id, tenant_id, idempotency_key, input_fingerprint, operation, status, request_json, submitted_by)
   VALUES (:run_id, :tenant_id, :idempotency_key, :input_fingerprint, :operation, 'Running', :request_json, :submitted_by)
   ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
   RETURNING run_id;
   ```
2. **Atomic Quota Debit**:
   ```sql
   INSERT INTO daily_usage (tenant_id, usage_date_utc, accepted_runs)
   VALUES (:tenant_id, :usage_date, 1)
   ON CONFLICT (tenant_id, usage_date_utc)
   DO UPDATE SET accepted_runs = daily_usage.accepted_runs + 1
   WHERE daily_usage.accepted_runs < :limit
   RETURNING accepted_runs;
   ```

**Explanation**:
Both queries run within a single transaction in `accept_run()`. If the idempotency key already exists, step 1 returns zero rows and triggers a replay lookup. If daily quota has reached the plan limit, step 2 updates zero rows, which causes an immediate rollback of the speculative `Running` record so no orphan row remains. Only when both steps succeed does `trans.commit()` persist the `Running` state before the processing logic runs.

### Azure SQL Equivalent (Conceptual Design)
For an Azure SQL implementation (described here per Section 2, but NOT implemented or tested):
```sql
BEGIN TRANSACTION;
BEGIN TRY
    INSERT INTO Runs (RunId, TenantId, IdempotencyKey, InputFingerprint, Operation, Status)
    VALUES (@RunId, @TenantId, @IdempotencyKey, @InputFingerprint, @Operation, 'Running');
END TRY
BEGIN CATCH
    IF ERROR_NUMBER() IN (2627, 2601) -- Duplicate key error
    BEGIN
        ROLLBACK TRANSACTION;
        -- Replay lookup ...
        RETURN;
    END
END CATCH;

UPDATE DailyUsage
SET AcceptedRuns = AcceptedRuns + 1
WHERE TenantId = @TenantId AND UsageDateUtc = @UsageDate AND AcceptedRuns < @Limit;

IF @@ROWCOUNT = 0
BEGIN
    ROLLBACK TRANSACTION; -- Quota exhausted
END
ELSE
BEGIN
    COMMIT TRANSACTION;
END
```

### POST /runs Check Order Pipeline

The `POST /runs` endpoint strictly executes the following sequence before any quota debit or execution occurs:

| Step | Check Description | HTTP Code on Failure | Implementing Function | File & Reference |
|:----:|:------------------|:--------------------:|:----------------------|:-----------------|
| **1** | Session authentication & JWT verification | `401 Unauthorized` | `get_current_user` | `app/auth.py` |
| **2** | Tenant override in headers or query params | `400 Bad Request` | `check_tenant_override` | `app/auth.py` |
| **3** | Role authorization (Operator only) | `403 Forbidden` | Inline role check | `app/routes.py` |
| **4** | Subscription status not `Suspended` | `403 Forbidden` | Inline status check | `app/routes.py` |
| **5** | `Idempotency-Key` header present (1–128 chars) | `400 Bad Request` | Inline header check | `app/routes.py` |
| **6** | Raw body <= 64 KiB, valid JSON shape, 1–10 records, record schema, body tenant override | `400 Bad Request` | Inline body parser & `check_tenant_override` | `app/routes.py` |
| **7** | Plan entitlement check (Basic cannot `process`) | `403 Forbidden` | `require_plan_entitlement` | `app/routes.py` |
| **8** | For `process` only: validate records (any invalid row rejects before run or debit) | `400 Bad Request` | `validate_records` | `app/validation.py` |
| **9** | Idempotency replay lookup on `(tenant, key)`: different fingerprint (`409`), in-progress (`409`), terminal (`200` replay, no debit) | `200` / `409` | `accept_run` | `app/service.py` |
| **10** | Atomic accept transaction: claim key & debit quota slot in 1 transaction | `429 Too Many Requests` | `accept_run` | `app/service.py` |
| **11** | Commit durable `Running` state, execute test hook / processor, persist `Succeeded` or `Failed` | `201 Created` | `finish_run` | `app/service.py` |

---

## 5. Evidence

Evidence for the checks that were run is in the evidence/ folder (see evidence/INDEX.md). A01 (cloud deployment) and A12 (fresh-session replay of SKILL.md) are pending.

---

## 6. Quickstart Guide (Local Setup)

### Prerequisites
- Python 3.11 or 3.12
- Node.js 20+ and npm
- PostgreSQL database (e.g. Neon serverless)

### Step 1: Clone and Create Virtual Environment
```bash
git clone <REPO_URL> Customer_SaaS_application
cd Customer_SaaS_application

python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\activate
# On Linux / macOS / Git Bash:
source .venv/bin/activate

pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
```bash
cp .env.example .env
# Edit .env:
# 1. DATABASE_URL (must use postgresql+psycopg:// scheme):
#    - Cloud Neon / Azure: postgresql+psycopg://user:password@host/dbname?sslmode=require
#    - Local Postgres:     postgresql+psycopg://postgres:postgres@localhost:5432/customer_saas
# 2. JWT_SECRET: generate a 48-byte URL-safe secret (must be >= 32 characters):
#    python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Step 3: Run Database Migrations
```bash
alembic upgrade head
```

### Step 4: Build Frontend
```bash
cd web
npm install
npm run build
cd ..
```

### Step 5: Run Automated Tests
```bash
# Run full pytest suite (63 tests)
pytest -v
```

### Step 6: Start Server
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Step 7: Mint Token & Test in Browser
In a separate terminal:
```bash
# Mint session token for Acme Pro Operator
python scripts/harness.py mint-token acme:Operator

# Open http://127.0.0.1:8000/?token=<MINTED_TOKEN>
```

---

## 7. Security & Tenancy Guarantees

1. **Token-Only Tenancy**:
   - `tenant_id` and `role` are strictly extracted from verified HS256 JWT claims. Any tenant parameter in request body, URL query string, or HTTP headers triggers an immediate HTTP 400 `TENANT_OVERRIDE_REJECTED`.
2. **Identical 404 Responses**:
   - Requests for unknown runs or runs owned by another tenant return an identical JSON body `{"error": {"code": "RUN_NOT_FOUND", "message": "Run not found."}}`, preventing tenant enumeration attacks.
3. **Secret Hygiene**:
   - Secrets are passed exclusively via environment variables (`.env` or `TF_VAR_*`).
   - `.env`, `.terraform`, `.tfstate`, and runtime tokens are strictly gitignored and excluded from version control.
   - Evidence logs (`evidence/*.json`) are sanitized through regex redactors before persistence.
