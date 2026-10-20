# A12 — Teammate Replay (PENDING)

**Status**: PENDING — requires a second team member running from a fresh clone.

## What Will Be Stored Here

Once a teammate performs a clean-clone replay following `skills/customer-quality/SKILL.md`, this folder will contain:

1. **replay-log.txt** — Redacted transcript of the teammate's session, showing:
   - Fresh clone (`git clone <repo> && cd Customer_SaaS_application`)
   - `pip install -r requirements.txt` and `alembic upgrade head`
   - Token minted via `python scripts/harness.py mint-token acme:Operator`
   - Successful `POST /runs` with the valid fixture (HTTP 201, Succeeded)
   - Invalid fixture submission returning HTTP 400 with R1–R4 issues
   - Forced-failure check (`X-Force-Failure: 1` with `ENABLE_TEST_HOOKS=true`) returning HTTP 201 Failed
   - All tokens, passwords, and connection strings redacted

## Steps for Teammate (from SKILL.md)

```bash
# 1. Clone the repo (use the shared GitHub URL)
git clone <REPO_URL> Customer_SaaS_application
cd Customer_SaaS_application

# 2. Set up environment
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure .env (get DATABASE_URL and JWT_SECRET from the team)
cp .env.example .env
# Edit .env — do NOT commit

# 4. Run migrations
alembic upgrade head

# 5. Build frontend
cd web && npm install && npm run build && cd ..

# 6. Start server
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 7. In another terminal — mint token
python scripts/harness.py mint-token acme:Operator
# Token printed to terminal only, never written to file

# 8. Test valid fixture
curl -s -X POST http://127.0.0.1:8000/runs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Idempotency-Key: a12-valid-001" \
  -H "Content-Type: application/json" \
  -d @fixtures/valid.json

# 9. Test forced failure (ENABLE_TEST_HOOKS must be true in .env)
curl -s -X POST http://127.0.0.1:8000/runs \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Idempotency-Key: a12-forced-001" \
  -H "X-Force-Failure: 1" \
  -H "Content-Type: application/json" \
  -d @fixtures/valid.json
```
