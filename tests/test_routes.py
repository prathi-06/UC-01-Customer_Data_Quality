import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app import config
from app.db import engine
from app.routes import require_plan_entitlement
from scripts.harness import (
    mint_token,
    reset_runs,
    reset_quota,
    suspend_tenant,
    activate_tenant,
    change_plan
)
from app.subscriptions import get_subscription

client = TestClient(app)

def test_exact_six_api_routes():
    """Verify that only the exact six specified API routes are exposed by FastAPI."""
    expected_routes = {
        ("GET", "/health"),
        ("GET", "/tools"),
        ("GET", "/subscription"),
        ("POST", "/runs"),
        ("GET", "/runs"),
        ("GET", "/runs/{run_id}/result"),
    }

    actual_routes = set()
    for route in app.routes:
        # StaticFiles mount is allowed, check API route paths
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method not in ("HEAD", "OPTIONS"):
                    actual_routes.add((method, route.path))

    # All expected routes must be present and match exactly
    assert actual_routes == expected_routes

    # Check documentation and schema routes are disabled
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404

    # Check no admin, reset, or debug routes exist
    assert client.get("/admin").status_code == 404
    assert client.get("/reset").status_code == 404
    assert client.post("/reset").status_code in (404, 405)
    assert client.get("/debug").status_code == 404
    assert client.post("/runs/reset").status_code in (404, 405)


def test_force_failure_hook_behaviour(monkeypatch):
    """
    Verify X-Force-Failure is honoured when ENABLE_TEST_HOOKS is true,
    and completely ignored when ENABLE_TEST_HOOKS is false.
    """
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    payload = {
        "operation": "validate",
        "records": [
            {"record_id": "T01", "email": "t1@example.com", "credit_limit": 100, "status": "ACTIVE"}
        ]
    }

    # Case 1: ENABLE_TEST_HOOKS = True -> X-Force-Failure is honoured
    monkeypatch.setattr(config, "ENABLE_TEST_HOOKS", True)
    res_forced = client.post(
        "/runs",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "force-fail-key-true",
            "X-Force-Failure": "1"
        }
    )
    assert res_forced.status_code == 201
    body_forced = res_forced.json()
    assert body_forced["status"] == "Failed"
    assert body_forced["error"] == "PROCESSING_FAILED"

    # Case 2: ENABLE_TEST_HOOKS = False -> X-Force-Failure is ignored
    monkeypatch.setattr(config, "ENABLE_TEST_HOOKS", False)
    res_ignored = client.post(
        "/runs",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": "force-fail-key-false",
            "X-Force-Failure": "1"
        }
    )
    assert res_ignored.status_code == 201
    body_ignored = res_ignored.json()
    assert body_ignored["status"] == "Succeeded"
    assert "result" in body_ignored
    assert body_ignored["result"]["valid_rows"] == 1


def test_require_plan_entitlement_function():
    """Unit test for the require_plan_entitlement guard function."""
    basic_sub = {"plan": "Basic", "allowed_operations": ["validate"]}
    pro_sub = {"plan": "Pro", "allowed_operations": ["validate", "process"]}

    # Basic allowed validate
    assert require_plan_entitlement(basic_sub, "validate") is None
    # Basic disallowed process -> returns 403 response
    err_resp = require_plan_entitlement(basic_sub, "process")
    assert err_resp is not None
    assert err_resp.status_code == 403
    data = json.loads(err_resp.body.decode("utf-8"))
    assert data["error"]["code"] == "OPERATION_NOT_ALLOWED"

    # Pro allowed both
    assert require_plan_entitlement(pro_sub, "validate") is None
    assert require_plan_entitlement(pro_sub, "process") is None


def test_body_bounds_and_malformed_shapes_reject_400_no_debit():
    """
    Test edge cases for request bodies:
    - > 64 KiB
    - 0 rows
    - 11 rows
    - missing fields
    - extra body fields
    - extra record fields
    - non-object body
    - records not a list
    - bad operation
    All must return 400 and debit 0 slots.
    """
    reset_runs("globex")
    reset_quota("globex")
    token = mint_token("globex:Operator")
    base_headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "body-bound-test"}

    # 1. Non-object body (e.g. array)
    r = client.post("/runs", content="[1, 2, 3]", headers={**base_headers, "Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_BODY"

    # 2. Over 64 KiB
    large_payload = {
        "operation": "validate",
        "records": [
            {"record_id": "C01", "email": "a" * 70000 + "@example.com", "credit_limit": 100, "status": "ACTIVE"}
        ]
    }
    r = client.post("/runs", json=large_payload, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    # 3. 0 rows
    r = client.post("/runs", json={"operation": "validate", "records": []}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_RECORDS"

    # 4. 11 rows
    eleven = [
        {"record_id": f"R{i:02d}", "email": f"u{i}@test.com", "credit_limit": 100, "status": "ACTIVE"}
        for i in range(11)
    ]
    r = client.post("/runs", json={"operation": "validate", "records": eleven}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_RECORDS"

    # 5. Missing body fields (no operation)
    r = client.post("/runs", json={"records": eleven[:1]}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_FIELDS"

    # 6. Missing body fields (no records)
    r = client.post("/runs", json={"operation": "validate"}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_FIELDS"

    # 7. Extra body field
    r = client.post("/runs", json={"operation": "validate", "records": eleven[:1], "extra_field": True}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_FIELDS"

    # 8. Extra record field
    bad_record = dict(eleven[0])
    bad_record["extra_col"] = "unexpected"
    r = client.post("/runs", json={"operation": "validate", "records": [bad_record]}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_RECORD_FIELDS"

    # 9. Bad operation
    r = client.post("/runs", json={"operation": "purge", "records": eleven[:1]}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_OPERATION"

    # 10. Records is not a list (e.g. string)
    r = client.post("/runs", json={"operation": "validate", "records": "not a list"}, headers=base_headers)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_RECORDS"

    # Quota check: 0 used
    sub = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()
    assert sub["used_today"] == 0


def test_replay_running_returns_409():
    """Replaying an idempotency key whose run is in Running state returns 409 RUN_IN_PROGRESS."""
    reset_runs("acme")
    reset_quota("acme")
    token = mint_token("acme:Operator")
    valid_record = [{"record_id": "C01", "email": "alice@test.com", "credit_limit": 100, "status": "ACTIVE"}]
    payload = {"operation": "validate", "records": valid_record}
    key = "test-running-state-key"

    # Insert a run directly in 'Running' state
    import hashlib
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    import uuid
    run_id = str(uuid.uuid4())

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO runs (run_id, tenant_id, idempotency_key, input_fingerprint, operation, status)
                VALUES (:rid, :tid, :key, :fp, :op, 'Running')
            """),
            {
                "rid": run_id,
                "tid": "acme",
                "key": key,
                "fp": fingerprint,
                "op": "validate"
            }
        )

    # Now make the POST request with the same key and payload
    res = client.post(
        "/runs",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": key}
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "RUN_IN_PROGRESS"


def test_harness_verbs():
    """Verify each harness management function operates correctly."""
    # 1. mint-token
    tok = mint_token("acme:Operator")
    assert tok and isinstance(tok, str)

    # 2. set-plan & change-plan
    change_plan("globex", "Pro")
    sub = get_subscription("globex")
    assert sub["plan"] == "Pro"
    assert sub["daily_quota"] == 10

    change_plan("globex", "Basic")
    sub = get_subscription("globex")
    assert sub["plan"] == "Basic"
    assert sub["daily_quota"] == 3

    # 3. suspend & activate
    suspend_tenant("globex")
    sub = get_subscription("globex")
    assert sub["status"] == "Suspended"

    activate_tenant("globex")
    sub = get_subscription("globex")
    assert sub["status"] == "Active"

    # 4. reset-runs & reset-quota
    reset_runs("globex")
    reset_quota("globex")
    with engine.connect() as conn:
        r_count = conn.execute(text("SELECT COUNT(*) FROM runs WHERE tenant_id = 'globex'")).scalar()
        q_count = conn.execute(text("SELECT COUNT(*) FROM daily_usage WHERE tenant_id = 'globex'")).scalar()
        assert r_count == 0
        assert q_count == 0


def test_basic_process_403_no_run_row_no_usage():
    """Verify Basic plan attempting 'process' returns 403 with no run row and no usage change in DB."""
    reset_runs("globex")
    reset_quota("globex")
    token = mint_token("globex:Operator")
    payload = {
        "operation": "process",
        "records": [
            {"record_id": "G01", "email": "g1@example.com", "credit_limit": 100, "status": "ACTIVE"}
        ]
    }

    # Query initial DB counts
    with engine.connect() as conn:
        initial_runs = conn.execute(text("SELECT COUNT(*) FROM runs WHERE tenant_id = 'globex'")).scalar()
        initial_usage = conn.execute(text("SELECT COUNT(*) FROM daily_usage WHERE tenant_id = 'globex'")).scalar()

    res = client.post(
        "/runs",
        json=payload,
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "basic-process-forbidden-key"}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "OPERATION_NOT_ALLOWED"

    # Query final DB counts: must remain zero
    with engine.connect() as conn:
        final_runs = conn.execute(text("SELECT COUNT(*) FROM runs WHERE tenant_id = 'globex'")).scalar()
        final_usage = conn.execute(text("SELECT COUNT(*) FROM daily_usage WHERE tenant_id = 'globex'")).scalar()
        assert final_runs == initial_runs == 0
        assert final_usage == initial_usage == 0

    # Subscription used quota must be 0
    sub = client.get("/subscription", headers={"Authorization": f"Bearer {token}"}).json()
    assert sub["used_today"] == 0

