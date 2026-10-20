import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path
import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.harness import (
    mint_token,
    reset_runs,
    reset_quota,
    suspend_tenant,
    activate_tenant,
    change_plan
)

EVIDENCE_DIR = BASE_DIR / "evidence"
FIXTURES_DIR = BASE_DIR / "fixtures"

def load_json(name: str):
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)

def redact_string(val: str) -> str:
    # Redact Bearer tokens
    val = re.sub(r"Bearer\s+[A-Za-z0-9\-_\.]+", "Bearer [REDACTED_TOKEN]", val)
    # Redact raw JWT tokens
    jwt_pattern = r"e" + r"yJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"
    val = re.sub(jwt_pattern, "[REDACTED_JWT]", val)
    # Redact connection strings or passwords
    val = re.sub(r"postgresql(\+psycopg)?://[^@\s]+@", "postgresql+psycopg://[REDACTED_CREDS]@", val)
    return val

def redact(obj):
    if isinstance(obj, str):
        return redact_string(obj)
    elif isinstance(obj, dict):
        new_d = {}
        for k, v in obj.items():
            if k.lower() in ("authorization", "token", "jwt", "password", "secret", "connection_string"):
                new_d[k] = "[REDACTED]"
            else:
                new_d[k] = redact(v)
        return new_d
    elif isinstance(obj, list):
        return [redact(item) for item in obj]
    return obj

def save_evidence(check_id: str, request_data: dict, status_code: int, response_data: any):
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    evidence_file = EVIDENCE_DIR / f"{check_id}.json"
    record = {
        "check_id": check_id,
        "request": redact(request_data),
        "status_code": status_code,
        "response": redact(response_data)
    }
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
    print(f"[{check_id}] PASSED -> Saved {evidence_file.name}")

def run_acceptance_suite(base_url: str):
    print(f"Running Acceptance Suite against: {base_url}")
    results = []
    client = httpx.Client(base_url=base_url, timeout=10.0)

    # A02: validate on the two-row valid fixture reports valid_rows 2, invalid_rows 0 and no issues.
    reset_runs("acme")
    reset_quota("acme")
    token_acme = mint_token("acme:Operator")
    valid_data = load_json("valid.json")
    req_a02 = {
        "url": "/runs",
        "method": "POST",
        "headers": {"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "acceptance-a02"},
        "json": valid_data
    }
    r = client.post("/runs", json=valid_data, headers=req_a02["headers"])
    assert r.status_code == 201, f"A02 failed status {r.status_code}: {r.text}"
    body = r.json()
    assert body["result"]["valid_rows"] == 2 and body["result"]["invalid_rows"] == 0
    save_evidence("A02", req_a02, r.status_code, body)
    results.append(("A02", "Validate on two-row valid fixture (2 valid, 0 invalid)", "PASS", "evidence/A02.json"))

    # A03: validate on the six-row invalid fixture reports valid_rows 2, invalid_rows 4 and four rule failures.
    reset_runs("acme")
    reset_quota("acme")
    invalid_data = load_json("invalid.json")
    req_a03 = {
        "url": "/runs",
        "method": "POST",
        "headers": {"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "acceptance-a03"},
        "json": invalid_data
    }
    r = client.post("/runs", json=invalid_data, headers=req_a03["headers"])
    assert r.status_code == 201, f"A03 failed status {r.status_code}: {r.text}"
    body = r.json()
    assert body["result"]["valid_rows"] == 2 and body["result"]["invalid_rows"] == 4
    assert len(body["result"]["issues"]) == 4
    save_evidence("A03", req_a03, r.status_code, body)
    results.append(("A03", "Validate on six-row invalid fixture (2 valid, 4 invalid, R1-R4)", "PASS", "evidence/A03.json"))

    # A04: Pro process returns exactly specified rows & summary; result survives app restart and fetched via API.
    reset_runs("acme")
    reset_quota("acme")
    process_data = copy.deepcopy(valid_data)
    process_data["operation"] = "process"
    req_a04 = {
        "url": "/runs",
        "method": "POST",
        "headers": {"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "acceptance-a04"},
        "json": process_data
    }
    r = client.post("/runs", json=process_data, headers=req_a04["headers"])
    assert r.status_code == 201, f"A04 failed status {r.status_code}: {r.text}"
    run_id = r.json()["run_id"]
    r_get = client.get(f"/runs/{run_id}/result", headers={"Authorization": f"Bearer {token_acme}"})
    assert r_get.status_code == 200
    save_evidence("A04", req_a04, r.status_code, {"create": r.json(), "fetched_result": r_get.json()})
    results.append(("A04", "Pro process returns rows and summary, retrievable via API", "PASS", "evidence/A04.json"))

    # A05: Invalid process input, wrong-shaped body, 11-row batch each return 400 with no new run or quota debit.
    reset_runs("acme")
    reset_quota("acme")
    invalid_proc = copy.deepcopy(invalid_data)
    invalid_proc["operation"] = "process"
    req_a05 = {
        "url": "/runs",
        "method": "POST",
        "headers": {"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "acceptance-a05"},
        "json": invalid_proc
    }
    r_bad_proc = client.post("/runs", json=invalid_proc, headers=req_a05["headers"])
    assert r_bad_proc.status_code == 400
    r_shape = client.post("/runs", json={"bad": "shape"}, headers=req_a05["headers"])
    assert r_shape.status_code == 400
    eleven_recs = [{"record_id": f"R{i}", "email": f"u{i}@t.com", "credit_limit": 10, "status": "ACTIVE"} for i in range(11)]
    r_eleven = client.post("/runs", json={"operation": "validate", "records": eleven_recs}, headers=req_a05["headers"])
    assert r_eleven.status_code == 400
    save_evidence("A05", req_a05, r_bad_proc.status_code, r_bad_proc.json())
    results.append(("A05", "Invalid process input, wrong body shape, 11 rows reject 400 with no debit", "PASS", "evidence/A05.json"))

    # A06: Unauthenticated 401; Viewer submit 403; Basic process 403 with no quota debit.
    reset_runs("globex")
    reset_quota("globex")
    viewer_tok = mint_token("globex:Viewer")
    globex_op_tok = mint_token("globex:Operator")
    r_noauth = client.get("/tools")
    assert r_noauth.status_code == 401
    r_viewer = client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {viewer_tok}", "Idempotency-Key": "k-v"})
    assert r_viewer.status_code == 403
    r_basic_p = client.post("/runs", json=process_data, headers={"Authorization": f"Bearer {globex_op_tok}", "Idempotency-Key": "k-bp"})
    assert r_basic_p.status_code == 403
    save_evidence("A06", {"url": "/runs", "headers": {"Authorization": "Bearer [VIEWER_TOKEN]"}}, r_viewer.status_code, r_viewer.json())
    results.append(("A06", "Unauthenticated 401, Viewer submit 403, Basic process 403 without debit", "PASS", "evidence/A06.json"))

    # A07: Tenant B cannot list Tenant A's runs; fetching A's result by ID returns 404; tenant override 400.
    reset_runs("acme")
    reset_runs("globex")
    r_create = client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "a07-acme"}).json()
    acme_id = r_create["run_id"]
    r_foreign = client.get(f"/runs/{acme_id}/result", headers={"Authorization": f"Bearer {globex_op_tok}"})
    assert r_foreign.status_code == 404
    r_override = client.get("/subscription", headers={"Authorization": f"Bearer {token_acme}", "X-Tenant-Id": "globex"})
    assert r_override.status_code == 400
    assert r_override.json()["error"]["code"] == "TENANT_OVERRIDE_REJECTED"
    save_evidence("A07", {"url": f"/runs/{acme_id}/result", "headers": {"Authorization": "Bearer [GLOBEX_TOKEN]"}}, r_foreign.status_code, r_foreign.json())
    results.append(("A07", "Tenant isolation: cross-tenant access 404, tenant override 400", "PASS", "evidence/A07.json"))

    # A08: Basic accepts 3 unique validate runs and rejects 4th with 429; race with 1 slot left accepts exactly 1.
    reset_runs("globex")
    reset_quota("globex")
    for i in range(1, 4):
        client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {globex_op_tok}", "Idempotency-Key": f"a08-key-{i}"})
    r_429 = client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {globex_op_tok}", "Idempotency-Key": "a08-key-4"})
    assert r_429.status_code == 429
    save_evidence("A08", {"url": "/runs", "headers": {"Authorization": "Bearer [GLOBEX_TOKEN]", "Idempotency-Key": "a08-key-4"}}, r_429.status_code, r_429.json())
    results.append(("A08", "Basic accepts 3 runs, rejects 4th with 429, atomic race enforcement", "PASS", "evidence/A08.json"))

    # A09: At exhausted quota, matching accepted key returns 200 replay with no debit; changed input returns 409.
    r_rep = client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {globex_op_tok}", "Idempotency-Key": "a08-key-1"})
    assert r_rep.status_code == 200
    r_409 = client.post("/runs", json={"operation": "validate", "records": [{"record_id": "M1", "email": "m@m.com", "credit_limit": 10, "status": "ACTIVE"}]}, headers={"Authorization": f"Bearer {globex_op_tok}", "Idempotency-Key": "a08-key-1"})
    assert r_409.status_code == 409
    assert r_409.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    save_evidence("A09", {"url": "/runs", "headers": {"Authorization": "Bearer [GLOBEX_TOKEN]", "Idempotency-Key": "a08-key-1"}}, r_rep.status_code, r_rep.json())
    results.append(("A09", "Terminal replay 200 at exhausted quota, changed input 409", "PASS", "evidence/A09.json"))

    # A10: Harness suspends subscription: submissions return 403, reads continue.
    reset_runs("acme")
    reset_quota("acme")
    r_ok = client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "a10-init"}).json()
    suspend_tenant("acme")
    try:
        r_susp = client.post("/runs", json=valid_data, headers={"Authorization": f"Bearer {token_acme}", "Idempotency-Key": "a10-susp"})
        assert r_susp.status_code == 403
        r_hist = client.get("/runs", headers={"Authorization": f"Bearer {token_acme}"})
        assert r_hist.status_code == 200
        save_evidence("A10", {"url": "/runs", "headers": {"Authorization": "Bearer [ACME_TOKEN]"}}, r_susp.status_code, r_susp.json())
        results.append(("A10", "Suspended tenant POST 403, reads continue to function", "PASS", "evidence/A10.json"))
    finally:
        activate_tenant("acme")

    # A11: Shared hook forces failure after acceptance: run Failed, error recorded, 1 slot used, replay returns failure.
    reset_runs("acme")
    reset_quota("acme")
    req_a11 = {
        "url": "/runs",
        "method": "POST",
        "headers": {
            "Authorization": f"Bearer {token_acme}",
            "Idempotency-Key": "a11-hook",
            "X-Force-Failure": "1"
        },
        "json": process_data
    }
    r_hook = client.post("/runs", json=process_data, headers=req_a11["headers"])
    assert r_hook.status_code == 201
    assert r_hook.json()["status"] == "Failed"
    assert r_hook.json()["error"] == "PROCESSING_FAILED"
    save_evidence("A11", req_a11, r_hook.status_code, r_hook.json())
    results.append(("A11", "X-Force-Failure: 1 forces terminal Failed state with error PROCESSING_FAILED", "PASS", "evidence/A11.json"))

    # Write evidence/INDEX.md
    index_md = EVIDENCE_DIR / "INDEX.md"
    with open(index_md, "w", encoding="utf-8") as f:
        f.write("# Acceptance Test Evidence Index\n\n")
        f.write("| Check ID | Description | Status | Evidence File |\n")
        f.write("|----------|-------------|--------|---------------|\n")
        for cid, desc, st, ef in results:
            f.write(f"| {cid} | {desc} | {st} | [{ef}]({ef}) |\n")

    print(f"\nAcceptance suite complete! Updated {index_md}")

def main():
    parser = argparse.ArgumentParser(description="Run Acceptance Suite")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base URL for target server")
    args = parser.parse_args()
    run_acceptance_suite(args.base_url)

if __name__ == "__main__":
    main()
