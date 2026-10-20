import enum
import hashlib
import json
import uuid
from datetime import datetime, timezone, date
from typing import Any, Callable, Dict, List, Optional, Tuple
from sqlalchemy import text
from app.db import engine

class AcceptStatus(enum.Enum):
    ACCEPTED = "ACCEPTED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    REPLAY_TERMINAL = "REPLAY_TERMINAL"
    REPLAY_RUNNING = "REPLAY_RUNNING"
    REPLAY_CONFLICT = "REPLAY_CONFLICT"

def default_utc_clock() -> date:
    return datetime.now(timezone.utc).date()

def compute_fingerprint(operation: str, records: Any) -> str:
    canonical = json.dumps({"operation": operation, "records": records}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def accept_run(
    tenant_id: str,
    idempotency_key: str,
    operation: str,
    records: Any,
    quota_limit: int,
    clock: Optional[Callable[[], date]] = None,
    submitted_by: Optional[str] = None,
    engine_override = None
) -> Tuple[AcceptStatus, Optional[str], Optional[Dict[str, Any]]]:
    """
    Executes accept_run as ONE transaction per spec:
    (a) INSERT into runs with status Running ... ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING run_id;
        no row returned means key exists -> rollback and return replay result.
    (b) INSERT INTO daily_usage (tenant_id, usage_date_utc, accepted_runs) VALUES (:t,:d,1)
        ON CONFLICT (tenant_id, usage_date_utc) DO UPDATE SET accepted_runs = daily_usage.accepted_runs + 1
        WHERE daily_usage.accepted_runs < :limit RETURNING accepted_runs;
        no row returned means quota exhausted -> rollback (claimed run disappears) and return QUOTA_EXHAUSTED.
    
    Returns:
        (AcceptStatus, run_id, run_data_if_replay)
    """
    db = engine_override or engine
    fingerprint = compute_fingerprint(operation, records)
    usage_date = (clock() if clock else default_utc_clock())

    with db.connect() as conn:
        trans = conn.begin()
        try:
            # (a) Attempt to insert running run
            new_run_id = str(uuid.uuid4())
            insert_run_sql = text("""
                INSERT INTO runs (run_id, tenant_id, idempotency_key, input_fingerprint, operation, status, request_json, submitted_by)
                VALUES (:run_id, :tenant_id, :idempotency_key, :input_fingerprint, :operation, 'Running', :request_json, :submitted_by)
                ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                RETURNING run_id;
            """)
            result = conn.execute(insert_run_sql, {
                "run_id": new_run_id,
                "tenant_id": tenant_id,
                "idempotency_key": idempotency_key,
                "input_fingerprint": fingerprint,
                "operation": operation,
                "request_json": json.dumps({"operation": operation, "records": records}),
                "submitted_by": submitted_by or "Operator"
            }).fetchone()

            # No row returned means idempotency key already exists for this tenant
            if not result:
                trans.rollback()
                # Lookup existing run for replay
                lookup_sql = text("""
                    SELECT run_id, tenant_id, idempotency_key, input_fingerprint, operation, status, result, result_json, error, error_message, created_at, completed_at, finished_at
                    FROM runs
                    WHERE tenant_id = :tenant_id AND idempotency_key = :idempotency_key
                """)
                existing = conn.execute(lookup_sql, {
                    "tenant_id": tenant_id,
                    "idempotency_key": idempotency_key
                }).mappings().fetchone()

                if not existing:
                    # Rare race condition edge case
                    return AcceptStatus.REPLAY_CONFLICT, None, None

                # Check fingerprint and operation match
                if existing["input_fingerprint"] != fingerprint or existing["operation"] != operation:
                    return AcceptStatus.REPLAY_CONFLICT, existing["run_id"], dict(existing)

                if existing["status"] == "Running":
                    return AcceptStatus.REPLAY_RUNNING, existing["run_id"], dict(existing)

                return AcceptStatus.REPLAY_TERMINAL, existing["run_id"], dict(existing)

            # (b) Run claimed; now claim quota atomically
            claim_quota_sql = text("""
                INSERT INTO daily_usage (tenant_id, usage_date_utc, accepted_runs)
                VALUES (:tenant_id, :usage_date_utc, 1)
                ON CONFLICT (tenant_id, usage_date_utc)
                DO UPDATE SET accepted_runs = daily_usage.accepted_runs + 1
                WHERE daily_usage.accepted_runs < :limit
                RETURNING accepted_runs;
            """)
            quota_res = conn.execute(claim_quota_sql, {
                "tenant_id": tenant_id,
                "usage_date_utc": usage_date,
                "limit": quota_limit
            }).fetchone()

            if not quota_res:
                # Quota exhausted: rollback so claimed run disappears
                trans.rollback()
                return AcceptStatus.QUOTA_EXHAUSTED, None, None

            # Both run insert and quota claim succeeded
            trans.commit()
            return AcceptStatus.ACCEPTED, new_run_id, None

        except Exception:
            trans.rollback()
            raise

def finish_run(
    run_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[Any] = None,
    engine_override = None
) -> None:
    """
    Updates the run status to Succeeded or Failed, persisting result and error.
    """
    db = engine_override or engine
    
    error_msg = None
    if isinstance(error, str):
        error_msg = error
    elif isinstance(error, dict):
        error_msg = error.get("message") or error.get("code") or json.dumps(error)

    sql = text("""
        UPDATE runs
        SET status = :status,
            result = :result,
            result_json = :result,
            error = :error,
            error_message = :error_message,
            finished_at = NOW(),
            completed_at = NOW()
        WHERE run_id = :run_id
    """)
    with db.begin() as conn:
        conn.execute(sql, {
            "run_id": run_id,
            "status": status,
            "result": json.dumps(result) if result is not None else None,
            "error": json.dumps(error) if error is not None else None,
            "error_message": error_msg
        })

def get_run(tenant_id: str, run_id: str, engine_override = None) -> Optional[Dict[str, Any]]:
    """
    Fetch a single run by run_id for the authorized tenant.
    """
    db = engine_override or engine
    sql = text("""
        SELECT run_id, tenant_id, idempotency_key, input_fingerprint, operation, status, result, error, created_at, finished_at
        FROM runs
        WHERE tenant_id = :tenant_id AND run_id = :run_id
    """)
    with db.connect() as conn:
        row = conn.execute(sql, {"tenant_id": tenant_id, "run_id": run_id}).mappings().fetchone()
        if not row:
            return None
        res = dict(row)
        if isinstance(res.get("result"), str):
            res["result"] = json.loads(res["result"])
        if isinstance(res.get("error"), str):
            res["error"] = json.loads(res["error"])
        return res

def list_runs(tenant_id: str, engine_override = None) -> List[Dict[str, Any]]:
    """
    List all runs for the authorized tenant, ordered newest first.
    """
    db = engine_override or engine
    sql = text("""
        SELECT run_id, tenant_id, idempotency_key, operation, status, created_at, finished_at
        FROM runs
        WHERE tenant_id = :tenant_id
        ORDER BY created_at DESC
    """)
    with db.connect() as conn:
        rows = conn.execute(sql, {"tenant_id": tenant_id}).mappings().fetchall()
        return [dict(r) for r in rows]

def get_daily_usage(tenant_id: str, usage_date: Optional[date] = None, engine_override = None) -> int:
    """
    Return accepted_runs for a tenant on the given UTC date (defaults to today).
    """
    db = engine_override or engine
    d = usage_date or default_utc_clock()
    sql = text("""
        SELECT accepted_runs FROM daily_usage
        WHERE tenant_id = :tenant_id AND usage_date_utc = :usage_date
    """)
    with db.connect() as conn:
        val = conn.execute(sql, {"tenant_id": tenant_id, "usage_date": d}).scalar()
        return val if val is not None else 0
