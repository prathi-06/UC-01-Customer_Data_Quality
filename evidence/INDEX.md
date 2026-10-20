# Acceptance Test Evidence Index

| Check ID | Description | Status | Environment | Evidence File | Date |
|----------|-------------|--------|-------------|---------------|------|
| A01 | Terraform validate, apply, /health, zero-drift plan | PENDING | cloud | [evidence/A01/README.md](A01/README.md) | — |
| A02 | Validate on two-row valid fixture (2 valid, 0 invalid) | PASS | local | [evidence/A02.json](A02.json) | 2026-10-20 |
| A03 | Validate on six-row invalid fixture (2 valid, 4 invalid, R1–R4) | PASS | local | [evidence/A03.json](A03.json) | 2026-10-20 |
| A04 | Pro process returns rows and summary, retrievable via API | PASS | local | [evidence/A04.json](A04.json) | 2026-10-20 |
| A05 | Invalid process input, wrong body shape, 11 rows reject 400 with no debit | PASS | local | [evidence/A05.json](A05.json) | 2026-10-20 |
| A06 | Unauthenticated 401, Viewer submit 403, Basic process 403 without debit | PASS | local | [evidence/A06.json](A06.json) | 2026-10-20 |
| A07 | Tenant isolation: cross-tenant access 404, tenant override 400 | PASS | local | [evidence/A07.json](A07.json) | 2026-10-20 |
| A08 | Basic accepts 3 runs, rejects 4th with 429, atomic race enforcement | PASS | local | [evidence/A08.json](A08.json) | 2026-10-20 |
| A09 | Terminal replay 200 at exhausted quota, changed input 409 | PASS | local | [evidence/A09.json](A09.json) | 2026-10-20 |
| A10 | Suspended tenant POST 403, reads continue to function | PASS | local | [evidence/A10.json](A10.json) | 2026-10-20 |
| A11 | X-Force-Failure: forces terminal Failed state; replay returns failure | PASS | local | [evidence/A11.json](A11.json) | 2026-10-20 |
| A12 | Teammate replay following SKILL.md | PENDING | cloud | [evidence/A12/README.md](A12/README.md) | — |

> **Note**: A02–A11 are local runs against the Neon PostgreSQL database. They are not cloud-deployment evidence; the brief does not award deployment marks for local runs. A01 and A12 will be completed after Azure deployment by the team.
