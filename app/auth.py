import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
import jwt
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from app.config import JWT_SECRET
from app.subscriptions import get_subscription

ALGORITHM = "HS256"

OVERRIDE_HEADER_NAMES = {"x-tenant-id", "x-tenant", "tenant", "tenant-id", "tenant_id"}
OVERRIDE_QUERY_NAMES = {"tenant_id", "tenant", "tenantid"}
OVERRIDE_BODY_KEYS = {"tenant_id", "tenant", "tenantid"}

def create_token(tenant_id: str, user: str, role: str, expires_in_hours: int = 8) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "tenant_id": tenant_id,
        "user": user,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_in_hours)).timestamp())
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)

def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        if "tenant_id" not in payload or "role" not in payload:
            raise jwt.InvalidTokenError("Missing required token claims")
        return payload
    except Exception as e:
        raise jwt.InvalidTokenError(str(e))

def check_tenant_override(request: Request, raw_body: Optional[bytes] = None) -> None:
    # 1. Check headers: any header containing 'tenant' (case-insensitive)
    for h in request.headers.keys():
        if "tenant" in h.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "TENANT_OVERRIDE_REJECTED", "message": "Tenant override in header is rejected."}}
            )

    # 2. Check query params: any param containing 'tenant' (case-insensitive)
    for q in request.query_params.keys():
        if "tenant" in q.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "TENANT_OVERRIDE_REJECTED", "message": "Tenant override in query is rejected."}}
            )

    # 3. Check JSON body keys: any key containing 'tenant' (case-insensitive)
    if raw_body:
        try:
            body_json = json.loads(raw_body.decode("utf-8"))
            if isinstance(body_json, dict):
                for k in body_json.keys():
                    if "tenant" in k.lower():
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={"error": {"code": "TENANT_OVERRIDE_REJECTED", "message": "Tenant override in body is rejected."}}
                        )
        except HTTPException:
            raise
        except Exception:
            pass

def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Extracts and verifies JWT Bearer token from Authorization header.
    Attaches user payload to request.state.user.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Missing or malformed Authorization header."}}
        )

    token = auth_header[len("Bearer "):].strip()
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "UNAUTHORIZED", "message": "Invalid or expired token."}}
        )

    request.state.user = payload
    return payload
