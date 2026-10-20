import json
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import JSONResponse

from app import config
from app.auth import get_current_user, check_tenant_override
from app.subscriptions import get_subscription
from app.validation import validate_records
from app.processor import process_records
from app.service import (
    accept_run,
    finish_run,
    get_run,
    list_runs,
    get_daily_usage,
    AcceptStatus
)

router = APIRouter()

def make_error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}}
    )

def require_plan_entitlement(sub: Dict[str, Any], operation: str) -> Optional[JSONResponse]:
    """CHECK 7: Verify tenant plan entitlement for requested operation."""
    if operation not in sub.get("allowed_operations", []):
        return make_error_response(
            status.HTTP_403_FORBIDDEN,
            "OPERATION_NOT_ALLOWED",
            f"Plan '{sub.get('plan')}' does not permit '{operation}'."
        )
    return None

@router.get("/health")
def health_check():
    """Public health check endpoint."""
    return {"status": "ok"}

@router.get("/tools")
def get_tools(request: Request):
    """Returns available tools and operations for the authenticated tenant."""
    check_tenant_override(request)
    user = get_current_user(request)
    sub = get_subscription(user["tenant_id"])
    if not sub:
        return make_error_response(status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant not found")

    return {
        "tenant_id": user["tenant_id"],
        "plan": sub["plan"],
        "allowed_operations": sub["allowed_operations"],
        "rules": ["R1", "R2", "R3", "R4"]
    }

@router.get("/subscription")
def get_tenant_subscription(request: Request):
    """Returns subscription details and remaining daily quota."""
    check_tenant_override(request)
    user = get_current_user(request)
    sub = get_subscription(user["tenant_id"])
    if not sub:
        return make_error_response(status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant not found")

    used_quota = get_daily_usage(user["tenant_id"])
    daily_quota = sub["daily_quota"]
    remaining_quota = max(0, daily_quota - used_quota)

    return {
        "tenant_id": user["tenant_id"],
        "name": sub.get("name", user["tenant_id"]),
        "plan": sub["plan"],
        "status": sub["status"],
        "daily_limit": daily_quota,
        "used_today": used_quota,
        "remaining": remaining_quota,
        "daily_quota": daily_quota,
        "used_quota": used_quota,
        "remaining_quota": remaining_quota,
        "allowed_operations": sub["allowed_operations"]
    }

@router.get("/runs")
def get_runs_history(request: Request):
    """Lists history of runs for the caller's tenant only."""
    check_tenant_override(request)
    user = get_current_user(request)
    runs = list_runs(user["tenant_id"])
    return {"runs": runs}

@router.get("/runs/{run_id}/result")
def get_run_result(run_id: str, request: Request):
    """Fetches result of a run for the authorized tenant."""
    check_tenant_override(request)
    user = get_current_user(request)
    
    # Validate UUID shape
    try:
        uuid.UUID(run_id)
    except Exception:
        return make_error_response(status.HTTP_404_NOT_FOUND, "RUN_NOT_FOUND", "Run not found.")

    run = get_run(user["tenant_id"], run_id)
    if not run:
        return make_error_response(status.HTTP_404_NOT_FOUND, "RUN_NOT_FOUND", "Run not found.")

    if run["status"] == "Failed":
        return {
            "run_id": run["run_id"],
            "status": "Failed",
            "error": run.get("error") or {"code": "RUN_FAILED", "message": "Run execution failed."}
        }

    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "result": run.get("result")
    }

@router.post("/runs")
def create_run(request: Request):
    """
    REQUIRED CHECK ORDER strictly enforced per spec:
    1. Authenticate user & attach tenant context (401 if missing/bad token)
    2. Check tenant override in headers and query params (400 if attempted)
    3. Read raw body bytes: check <= 64 KiB (400 if exceeded)
    4. Parse JSON body (400 if invalid JSON or wrong shape)
    5. Check tenant override in body JSON (400 if attempted)
    6. Check role: Operator only (403 if Viewer)
    7. Check subscription status: Active only (403 if Suspended)
    8. Check Idempotency-Key header: required nonempty (400 if missing)
    9. Validate body fields: operation ('validate'|'process') and records list of 1..10 (400 if invalid)
    10. Check plan entitlement: Basic cannot 'process' (403 if violated)
    11. For 'process', validate records: all must be valid (400 if any invalid row)
    12. Check idempotency replay before quota debit
    13. Atomic accept_run & quota debit (429 if quota exhausted)
    14. Check test hook X-Force-Failure (honoured only if ENABLE_TEST_HOOKS is true)
    15. Execute helper & persist finish_run -> return 201
    """
    # 1. Auth check (401)
    user = get_current_user(request)
    tenant_id = user["tenant_id"]

    # 2. Tenant override check on headers & query (400)
    try:
        check_tenant_override(request)
    except HTTPException as e:
        return make_error_response(e.status_code, e.detail["error"]["code"], e.detail["error"]["message"])

    # 3. Check role: Operator required (403)
    if user.get("role") != "Operator":
        return make_error_response(status.HTTP_403_FORBIDDEN, "FORBIDDEN_ROLE", "Viewer role is not permitted to submit runs.")

    # 4. Check subscription status: not Suspended (403)
    sub = get_subscription(tenant_id)
    if not sub:
        return make_error_response(status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "Tenant subscription not found.")

    if sub.get("status") == "Suspended":
        return make_error_response(status.HTTP_403_FORBIDDEN, "SUBSCRIPTION_SUSPENDED", "Tenant subscription is suspended.")

    # 5. Check Idempotency-Key header: present, 1 to 128 chars (400)
    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if not idempotency_key or len(idempotency_key) > 128:
        return make_error_response(status.HTTP_400_BAD_REQUEST, "MISSING_IDEMPOTENCY_KEY", "Idempotency-Key header is required and must be 1 to 128 characters.")

    # 6. Read raw body bytes (max 64 KiB = 65536 bytes) & check bounds and shape (400)
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        raw_body = loop.run_until_complete(request.body())
    except RuntimeError:
        raw_body = asyncio.run(request.body())

    if len(raw_body) > 65536:
        return make_error_response(status.HTTP_400_BAD_REQUEST, "PAYLOAD_TOO_LARGE", "Request body exceeds 64 KiB limit.")

    # Check tenant override in body (400)
    try:
        check_tenant_override(request, raw_body=raw_body)
    except HTTPException as e:
        return make_error_response(e.status_code, e.detail["error"]["code"], e.detail["error"]["message"])

    try:
        body = json.loads(raw_body.decode("utf-8"))
        if not isinstance(body, dict):
            return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_BODY", "Request body must be a JSON object.")
    except Exception:
        return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_JSON", "Request body contains invalid JSON.")

    allowed_body_keys = {"operation", "records"}
    if not set(body.keys()).issubset(allowed_body_keys) or "operation" not in body or "records" not in body:
        return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_FIELDS", "Body must contain exactly 'operation' and 'records'.")

    operation = body.get("operation")
    if operation not in ("validate", "process"):
        return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_OPERATION", "Operation must be 'validate' or 'process'.")

    records = body.get("records")
    if not isinstance(records, list) or len(records) < 1 or len(records) > 10:
        return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_RECORDS", "Records must be a list of 1 to 10 rows.")

    for r in records:
        if not isinstance(r, dict):
            return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_RECORD_FORMAT", "Each record must be an object.")
        if set(r.keys()) != {"record_id", "email", "credit_limit", "status"}:
            return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_RECORD_FIELDS", "Record fields must match schema exactly.")

    # 7. Check plan entitlement: Basic + process (403)
    # CHECK 7
    entitlement_error = require_plan_entitlement(sub, operation)
    if entitlement_error:
        return entitlement_error

    # 8. For process only: run the row rules, any invalid row (400, no run, no debit)
    if operation == "process":
        val_res = validate_records(records)
        if val_res["invalid_rows"] > 0:
            return make_error_response(status.HTTP_400_BAD_REQUEST, "INVALID_PROCESS_INPUT", "Process operation requires all records to be valid.")

    # 9 & 10. Atomic accept transaction & replay lookup
    quota_limit = sub["daily_quota"]
    status_code, run_id, replay_data = accept_run(
        tenant_id=tenant_id,
        idempotency_key=idempotency_key,
        operation=operation,
        records=records,
        quota_limit=quota_limit,
        submitted_by=user.get("user")
    )

    if status_code == AcceptStatus.QUOTA_EXHAUSTED:
        return make_error_response(status.HTTP_429_TOO_MANY_REQUESTS, "QUOTA_EXHAUSTED", "Daily run quota exhausted.")

    if status_code == AcceptStatus.REPLAY_CONFLICT:
        return make_error_response(status.HTTP_409_CONFLICT, "IDEMPOTENCY_KEY_REUSED", "Idempotency key reused with different input or operation.")

    if status_code == AcceptStatus.REPLAY_RUNNING:
        return make_error_response(status.HTTP_409_CONFLICT, "RUN_IN_PROGRESS", "Run with this idempotency key is currently in progress.")

    if status_code == AcceptStatus.REPLAY_TERMINAL:
        # 200 Replay
        rep_status = replay_data["status"]
        if rep_status == "Failed":
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={
                    "run_id": replay_data["run_id"],
                    "status": "Failed",
                    "error": replay_data.get("error_message") or replay_data.get("error") or "PROCESSING_FAILED"
                }
            )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "run_id": replay_data["run_id"],
                "status": rep_status,
                "result": replay_data.get("result_json") or replay_data.get("result")
            }
        )

    # 11. Run failure hook and processor, then set Succeeded or Failed -> return 201
    force_failure_hdr = request.headers.get("X-Force-Failure", "").strip()
    force_failure = force_failure_hdr in ("1", "true")
    if force_failure and config.ENABLE_TEST_HOOKS:
        error_msg = "PROCESSING_FAILED"
        finish_run(run_id, status="Failed", error=error_msg)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "run_id": run_id,
                "status": "Failed",
                "error": error_msg
            }
        )

    # 15. Execute helper
    try:
        if operation == "validate":
            result_payload = validate_records(records)
        else: # process
            result_payload = process_records(records)

        finish_run(run_id, status="Succeeded", result=result_payload)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "run_id": run_id,
                "status": "Succeeded",
                "result": result_payload
            }
        )
    except Exception as e:
        error_payload = {"code": "EXECUTION_ERROR", "message": str(e)}
        finish_run(run_id, status="Failed", error=error_payload)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "run_id": run_id,
                "status": "Failed",
                "error": error_payload
            }
        )
