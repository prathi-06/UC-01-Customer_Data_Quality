import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_token
from app.subscriptions import set_status, get_subscription
from scripts.harness import mint_token

client = TestClient(app)

PROTECTED_ROUTES = [
    ("GET", "/tools"),
    ("GET", "/subscription"),
    ("GET", "/runs"),
    ("GET", "/runs/00000000-0000-0000-0000-000000000000/result"),
    ("POST", "/runs"),
]

def test_health_public():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

@pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
def test_401_without_token(method, path):
    if method == "GET":
        res = client.get(path)
    else:
        res = client.post(path, json={})
    assert res.status_code == 401
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"

@pytest.mark.parametrize("method, path", PROTECTED_ROUTES)
def test_401_with_bad_token(method, path):
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    if method == "GET":
        res = client.get(path, headers=headers)
    else:
        res = client.post(path, json={}, headers=headers)
    assert res.status_code == 401
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"

def test_viewer_cannot_post():
    viewer_token = mint_token("acme:Viewer")
    headers = {
        "Authorization": f"Bearer {viewer_token}",
        "Idempotency-Key": "test-key-viewer-post"
    }
    payload = {
        "operation": "validate",
        "records": [{"record_id": "C01", "email": "a@b.com", "credit_limit": 100, "status": "ACTIVE"}]
    }
    res = client.post("/runs", json=payload, headers=headers)
    assert res.status_code == 403
    data = res.json()
    assert data["error"]["code"] == "FORBIDDEN_ROLE"

def test_suspended_tenant_post_gives_403_while_gets_work():
    try:
        set_status("acme", "Suspended")
        sub = get_subscription("acme")
        assert sub["status"] == "Suspended"

        operator_token = mint_token("acme:Operator")
        headers = {
            "Authorization": f"Bearer {operator_token}",
            "Idempotency-Key": "test-key-suspended"
        }
        payload = {
            "operation": "validate",
            "records": [{"record_id": "C01", "email": "a@b.com", "credit_limit": 100, "status": "ACTIVE"}]
        }

        # POST gives 403
        post_res = client.post("/runs", json=payload, headers=headers)
        assert post_res.status_code == 403
        assert post_res.json()["error"]["code"] == "SUBSCRIPTION_SUSPENDED"

        # GETs still work
        get_tools_res = client.get("/tools", headers={"Authorization": f"Bearer {operator_token}"})
        assert get_tools_res.status_code == 200

        get_sub_res = client.get("/subscription", headers={"Authorization": f"Bearer {operator_token}"})
        assert get_sub_res.status_code == 200

        get_runs_res = client.get("/runs", headers={"Authorization": f"Bearer {operator_token}"})
        assert get_runs_res.status_code == 200

    finally:
        set_status("acme", "Active")
        assert get_subscription("acme")["status"] == "Active"

def test_tenant_override_rejections():
    operator_token = mint_token("acme:Operator")
    base_headers = {"Authorization": f"Bearer {operator_token}"}

    # 1. Header override gives 400 TENANT_OVERRIDE_REJECTED
    res_header = client.get("/subscription", headers={**base_headers, "X-Tenant-Id": "globex"})
    assert res_header.status_code == 400
    assert res_header.json()["error"]["code"] == "TENANT_OVERRIDE_REJECTED"

    # 2. Query override gives 400 TENANT_OVERRIDE_REJECTED
    res_query = client.get("/subscription?tenant_id=globex", headers=base_headers)
    assert res_query.status_code == 400
    assert res_query.json()["error"]["code"] == "TENANT_OVERRIDE_REJECTED"

    # 3. Body override gives 400 TENANT_OVERRIDE_REJECTED
    body_override = {
        "tenant_id": "globex",
        "operation": "validate",
        "records": [{"record_id": "C01", "email": "a@b.com", "credit_limit": 100, "status": "ACTIVE"}]
    }
    res_body = client.post(
        "/runs",
        json=body_override,
        headers={**base_headers, "Idempotency-Key": "override-key"}
    )
    assert res_body.status_code == 400
    assert res_body.json()["error"]["code"] == "TENANT_OVERRIDE_REJECTED"
