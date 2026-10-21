import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import text
from app.auth import create_token
from app.db import engine
from app.subscriptions import get_store, set_status, set_plan, get_subscription

def load_seed() -> dict:
    seed_file = BASE_DIR / "seed.json"
    with open(seed_file, "r", encoding="utf-8") as f:
        return json.load(f)

def mint_token(user_identifier: str, expires_in_hours: int = 8) -> str:
    """
    user_identifier can be:
    - 'tenant:role' e.g. 'acme:Operator', 'globex:Viewer'
    - 'username' e.g. 'acme_operator', 'globex_viewer'
    """
    seed_data = load_seed()
    
    # Try username match
    for t in seed_data.get("tenants", []):
        for u in t.get("users", []):
            if u["username"].lower() == user_identifier.lower():
                return create_token(t["tenant_id"], u["username"], u["role"], expires_in_hours=expires_in_hours)

    # Try tenant:role match
    if ":" in user_identifier:
        t_id, role = user_identifier.split(":", 1)
        for t in seed_data.get("tenants", []):
            if t["tenant_id"].lower() == t_id.lower():
                for u in t.get("users", []):
                    if u["role"].lower() == role.lower():
                        return create_token(t["tenant_id"], u["username"], u["role"], expires_in_hours=expires_in_hours)
                # Fallback if tenant found but custom role
                return create_token(t["tenant_id"], f"{t['tenant_id']}_{role.lower()}", role, expires_in_hours=expires_in_hours)

    raise ValueError(f"User identifier '{user_identifier}' not found in seed.json")

def reset_runs(tenant_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM runs WHERE tenant_id = :t"), {"t": tenant_id})
    print(f"Reset runs for tenant: {tenant_id}")

def reset_quota(tenant_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM daily_usage WHERE tenant_id = :t"), {"t": tenant_id})
    print(f"Reset daily usage quota for tenant: {tenant_id}")

def suspend_tenant(tenant_id: str) -> None:
    if set_status(tenant_id, "Suspended"):
        print(f"Tenant {tenant_id} status set to Suspended.")
    else:
        print(f"Failed to find tenant {tenant_id}.")

def activate_tenant(tenant_id: str) -> None:
    if set_status(tenant_id, "Active"):
        print(f"Tenant {tenant_id} status set to Active.")
    else:
        print(f"Failed to find tenant {tenant_id}.")

def change_plan(tenant_id: str, plan: str) -> None:
    if set_plan(tenant_id, plan):
        print(f"Tenant {tenant_id} plan set to {plan}.")
    else:
        print(f"Failed to find tenant {tenant_id}.")

def main():
    parser = argparse.ArgumentParser(description="Test Harness for Customer Data Quality SaaS")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # mint-token
    mint_parser = subparsers.add_parser("mint-token")
    mint_parser.add_argument("user", help="Username or tenant:role (e.g. acme:Operator, globex:Viewer)")
    mint_parser.add_argument("--hours", type=int, default=8, help="Token expiration in hours (default 8)")

    # reset-runs
    reset_runs_p = subparsers.add_parser("reset-runs")
    reset_runs_p.add_argument("tenant_id", help="Tenant ID")

    # reset-quota
    reset_quota_p = subparsers.add_parser("reset-quota")
    reset_quota_p.add_argument("tenant_id", help="Tenant ID")

    # suspend
    suspend_p = subparsers.add_parser("suspend")
    suspend_p.add_argument("tenant_id", help="Tenant ID")

    # activate
    activate_p = subparsers.add_parser("activate")
    activate_p.add_argument("tenant_id", help="Tenant ID")

    # set-plan
    plan_p = subparsers.add_parser("set-plan")
    plan_p.add_argument("tenant_id", help="Tenant ID")
    plan_p.add_argument("plan", choices=["Basic", "Pro"], help="Plan name")

    args = parser.parse_args()

    if args.command == "mint-token":
        tok = mint_token(args.user, expires_in_hours=args.hours)
        print(tok)
    elif args.command == "reset-runs":
        reset_runs(args.tenant_id)
    elif args.command == "reset-quota":
        reset_quota(args.tenant_id)
    elif args.command == "suspend":
        suspend_tenant(args.tenant_id)
    elif args.command == "activate":
        activate_tenant(args.tenant_id)
    elif args.command == "set-plan":
        change_plan(args.tenant_id, args.plan)

if __name__ == "__main__":
    main()
