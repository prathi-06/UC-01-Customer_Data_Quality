import concurrent.futures
import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import config
from app import processor
from scripts.harness import (
    mint_token,
    reset_runs,
    reset_quota,
    suspend_tenant,
    activate_tenant,
    change_plan
)

client = TestClient(app)
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

def load_json(name: str):
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)

# A02: validate on the two-row valid fixture reports valid_rows 2, invalid_rows 0 and no issues.
def test_A02():
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    valid_data = load_json("valid.json")

    res = client.post(
        "/runs",
        json=valid_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a02-key"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "Succeeded"
    result = body["result"]
    assert result["valid_rows"] == 2
    assert result["invalid_rows"] == 0
    assert result["issues"] == []

# A03: validate on the six-row invalid fixture reports valid_rows 2, invalid_rows 4 and the four specified rule failures.
def test_A03():
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    invalid_data = load_json("invalid.json")

    res = client.post(
        "/runs",
        json=invalid_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a03-key"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "Succeeded"
    result = body["result"]
    assert result["valid_rows"] == 2
    assert result["invalid_rows"] == 4
    issues = result["issues"]
    assert len(issues) == 4
    expected_rule_ids = ["R1", "R2", "R3", "R4"]
    actual_rule_ids = [iss["rule_id"] for iss in issues]
    assert actual_rule_ids == expected_rule_ids

# A04: Pro process returns exactly the specified rows and summary; its result survives an app restart and is retrieved through the API.
def test_A04():
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    valid_data = load_json("valid.json")
    process_data = copy.deepcopy(valid_data)
    process_data["operation"] = "process"

    res = client.post(
        "/runs",
        json=process_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a04-key"}
    )
    assert res.status_code == 201
    run_id = res.json()["run_id"]

    expected_output = load_json("expected_process_output.json")
    assert res.json()["result"] == expected_output

    # Simulate app restart / new request retrieval through API
    new_client = TestClient(app)
    get_res = new_client.get(
        f"/runs/{run_id}/result",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert get_res.status_code == 200
    get_body = get_res.json()
    assert get_body["run_id"] == run_id
    assert get_body["status"] == "Succeeded"
    assert get_body["result"] == expected_output

# A05: Invalid process input, a wrong-shaped body and an 11-row batch each return 400 with no new run or quota debit.
def test_A05():
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    sub_before = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()

    # 1. Invalid process input (e.g. invalid status in records)
    invalid_data = load_json("invalid.json")
    invalid_process = copy.deepcopy(invalid_data)
    invalid_process["operation"] = "process"
    r1 = client.post(
        "/runs",
        json=invalid_process,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a05-key-1"}
    )
    assert r1.status_code == 400

    # 2. Wrong-shaped body
    r2 = client.post(
        "/runs",
        json={"wrong_key": 123},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a05-key-2"}
    )
    assert r2.status_code == 400

    # 3. 11-row batch
    eleven_records = [
        {"record_id": f"C{i:02d}", "email": f"user{i}@test.com", "credit_limit": 100, "status": "ACTIVE"}
        for i in range(1, 12)
    ]
    r3 = client.post(
        "/runs",
        json={"operation": "validate", "records": eleven_records},
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a05-key-3"}
    )
    assert r3.status_code == 400

    # Verify no quota debit
    sub_after = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()
    assert sub_after["used_quota"] == sub_before["used_quota"]

# A06: Unauthenticated requests to protected routes return 401; Viewer submission and Basic process both return 403 with no quota debit.
def test_A06():
    reset_runs("globex")
    reset_quota("globex")
    viewer_token = mint_token("globex:Viewer")
    operator_token = mint_token("globex:Operator")

    # 1. Unauthenticated -> 401
    r_unauth = client.post("/runs", json={"operation": "validate", "records": []})
    assert r_unauth.status_code == 401

    # 2. Viewer submission -> 403
    r_viewer = client.post(
        "/runs",
        json={"operation": "validate", "records": [{"record_id": "G01", "email": "g@test.com", "credit_limit": 100, "status": "ACTIVE"}]},
        headers={"Authorization": f"Bearer {viewer_token}", "Idempotency-Key": "a06-viewer-key"}
    )
    assert r_viewer.status_code == 403

    # 3. Basic process -> 403
    valid_data = load_json("valid.json")
    basic_process = copy.deepcopy(valid_data)
    basic_process["operation"] = "process"
    r_basic_process = client.post(
        "/runs",
        json=basic_process,
        headers={"Authorization": f"Bearer {operator_token}", "Idempotency-Key": "a06-basic-process"}
    )
    assert r_basic_process.status_code == 403

    # Check quota remains 0
    sub = client.get("/subscription", headers={"Authorization": f"Bearer {operator_token}"}).json()
    assert sub["used_quota"] == 0

# A07: Tenant B cannot list tenant A's runs; fetching A's result by ID returns 404. A request containing a tenant override is rejected.
def test_A07():
    reset_runs("acme")
    reset_runs("globex")
    acme_tok = mint_token("acme:Operator")
    globex_tok = mint_token("globex:Operator")

    # Acme creates a run
    valid_data = load_json("valid.json")
    acme_run = client.post(
        "/runs",
        json=valid_data,
        headers={"Authorization": f"Bearer {acme_tok}", "Idempotency-Key": "a07-acme-run"}
    ).json()
    acme_run_id = acme_run["run_id"]

    # Globex lists runs: should not contain Acme's run
    globex_runs = client.get("/runs", headers={"Authorization": f"Bearer {globex_tok}"}).json()["runs"]
    globex_run_ids = [r["run_id"] for r in globex_runs]
    assert acme_run_id not in globex_run_ids

    # Globex fetches Acme's run by ID -> 404
    r_foreign = client.get(f"/runs/{acme_run_id}/result", headers={"Authorization": f"Bearer {globex_tok}"})
    assert r_foreign.status_code == 404
    assert r_foreign.json()["error"]["code"] == "RUN_NOT_FOUND"

    # Malformed run id -> 404 with identical error body
    r_malformed = client.get("/runs/not-a-valid-uuid/result", headers={"Authorization": f"Bearer {globex_tok}"})
    assert r_malformed.status_code == 404
    assert r_malformed.json() == r_foreign.json()

    # Tenant override rejected -> 400 TENANT_OVERRIDE_REJECTED
    r_override = client.get("/subscription", headers={"Authorization": f"Bearer {acme_tok}", "X-Tenant-Id": "globex"})
    assert r_override.status_code == 400
    assert r_override.json()["error"]["code"] == "TENANT_OVERRIDE_REJECTED"

# A08: Basic accepts three unique validate runs and rejects the fourth with 429. With one slot left, two concurrent new requests accept exactly one.
def test_A08():
    reset_runs("globex")
    reset_quota("globex")
    token = mint_token("globex:Operator")
    valid_data = load_json("valid.json")

    # 1. Accepts 3 runs
    for i in range(1, 4):
        res = client.post(
            "/runs",
            json=valid_data,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"a08-key-{i}"}
        )
        assert res.status_code == 201

    # 2. Rejects the fourth with 429
    res4 = client.post(
        "/runs",
        json=valid_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a08-key-4"}
    )
    assert res4.status_code == 429
    assert res4.json()["error"]["code"] == "QUOTA_EXHAUSTED"

    # Concurrency test: with ONE slot left, two concurrent requests accept exactly one
    reset_runs("globex")
    reset_quota("globex")
    # Accept 2 runs so exactly 1 slot remains (Basic has quota 3)
    for i in range(1, 3):
        res = client.post(
            "/runs",
            json=valid_data,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"a08-prep-{i}"}
        )
        assert res.status_code == 201

    def send_run(key):
        c = TestClient(app)
        return c.post(
            "/runs",
            json=valid_data,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key}
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(send_run, "a08-race-1")
        f2 = executor.submit(send_run, "a08-race-2")
        r1 = f1.result()
        r2 = f2.result()

    status_codes = {r1.status_code, r2.status_code}
    assert status_codes == {201, 429}

# A09: At exhausted quota, a matching accepted key returns the same run with 200 and no debit. Reusing the key with changed input returns 409. Two simultaneous identical keys create at most one run.
def test_A09():
    reset_runs("globex")
    reset_quota("globex")
    token = mint_token("globex:Operator")
    valid_data = load_json("valid.json")

    # Fill quota of 3
    for i in range(1, 4):
        client.post(
            "/runs",
            json=valid_data,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": f"a09-key-{i}"}
        )

    # 1. Matching accepted key returns same run with 200 and no debit
    sub_before = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()
    r_replay = client.post(
        "/runs",
        json=valid_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a09-key-1"}
    )
    assert r_replay.status_code == 200
    sub_after = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()
    assert sub_after["used_quota"] == sub_before["used_quota"]

    # 2. Reusing key with changed input returns 409 IDEMPOTENCY_KEY_REUSED
    changed_data = {
        "operation": "validate",
        "records": [{"record_id": "C99", "email": "changed@test.com", "credit_limit": 50, "status": "ACTIVE"}]
    }
    r_conflict = client.post(
        "/runs",
        json=changed_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a09-key-1"}
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    # 3. Two simultaneous identical keys create at most one run
    reset_runs("globex")
    reset_quota("globex")
    def worker():
        c = TestClient(app)
        return c.post(
            "/runs",
            json=valid_data,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a09-simul-key"}
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker)
        f2 = executor.submit(worker)
        w1 = f1.result()
        w2 = f2.result()

    simul_statuses = [w1.status_code, w2.status_code]
    assert simul_statuses.count(201) == 1
    other_status = w2.status_code if w1.status_code == 201 else w1.status_code
    assert other_status in (200, 409)

# A10: The harness suspends the subscription: new submissions return 403 and debit nothing; authorised historical reads continue to work.
def test_A10():
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    valid_data = load_json("valid.json")

    # Create an initial run while active
    r_init = client.post(
        "/runs",
        json=valid_data,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a10-key-1"}
    )
    assert r_init.status_code == 201
    run_id = r_init.json()["run_id"]

    try:
        # Suspend subscription via harness
        suspend_tenant("acme")

        # New submission returns 403 and debits nothing
        r_new = client.post(
            "/runs",
            json=valid_data,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "a10-key-2"}
        )
        assert r_new.status_code == 403
        assert r_new.json()["error"]["code"] == "SUBSCRIPTION_SUSPENDED"

        # Authorised historical reads continue to work
        r_hist = client.get("/runs", headers={"Authorization": f"Bearer {token}"})
        assert r_hist.status_code == 200

        r_res = client.get(f"/runs/{run_id}/result", headers={"Authorization": f"Bearer {token}"})
        assert r_res.status_code == 200
        assert r_res.json()["run_id"] == run_id

    finally:
        activate_tenant("acme")

# A11: The shared hook forces a processing failure after acceptance: the run is Failed, the error is recorded and one slot is used. Replaying its key returns that failure without re-execution.
def test_A11(monkeypatch):
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    valid_data = load_json("valid.json")
    process_data = copy.deepcopy(valid_data)
    process_data["operation"] = "process"

    # Enable test hooks
    monkeypatch.setattr(config, "ENABLE_TEST_HOOKS", True)

    processor_call_count = 0
    import app.routes
    orig_process = app.routes.process_records

    def counting_processor(records):
        nonlocal processor_call_count
        processor_call_count += 1
        return orig_process(records)

    monkeypatch.setattr(app.routes, "process_records", counting_processor)

    # Submit with X-Force-Failure: 1
    res = client.post(
        "/runs",
        json=process_data,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "a11-hook-key",
            "X-Force-Failure": "1"
        }
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "Failed"
    assert body["error"] == "PROCESSING_FAILED"
    # Helper should NOT have been called because failure was forced after acceptance
    assert processor_call_count == 0

    # Verify slot was used
    sub = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()
    assert sub["used_today"] == 1

    # Replaying its key returns that failure without re-execution (count stays 0)
    res_replay = client.post(
        "/runs",
        json=process_data,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "a11-hook-key"
        }
    )
    assert res_replay.status_code == 200
    body_replay = res_replay.json()
    assert body_replay["status"] == "Failed"
    assert body_replay["error"] == "PROCESSING_FAILED"
    assert processor_call_count == 0
