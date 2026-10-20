import abc
import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from app.config import SUBSCRIPTION_STORE

PLAN_CONFIGS = {
    "Basic": {
        "daily_quota": 3,
        "allowed_operations": ["validate"]
    },
    "Pro": {
        "daily_quota": 10,
        "allowed_operations": ["validate", "process"]
    }
}

class SubscriptionStore(abc.ABC):
    @abc.abstractmethod
    def get_subscription(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def set_status(self, tenant_id: str, status: str) -> bool:
        pass

    @abc.abstractmethod
    def set_plan(self, tenant_id: str, plan: str) -> bool:
        pass

class FileSubscriptionStore(SubscriptionStore):
    def __init__(self, file_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent
        self.seed_path = base_dir / "seed.json"
        self.file_path = Path(file_path) if file_path else (base_dir / "subscriptions.json")
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.file_path.exists():
            if self.seed_path.exists():
                shutil.copy(self.seed_path, self.file_path)
            else:
                initial_data = {"tenants": []}
                with open(self.file_path, "w", encoding="utf-8") as f:
                    json.dump(initial_data, f, indent=2)

    def _load(self) -> Dict[str, Any]:
        self._ensure_file()
        with open(self.file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: Dict[str, Any]) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_subscription(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        data = self._load()
        for t in data.get("tenants", []):
            if t["tenant_id"] == tenant_id:
                plan = t.get("plan", "Basic")
                plan_cfg = PLAN_CONFIGS.get(plan, PLAN_CONFIGS["Basic"])
                return {
                    "tenant_id": t["tenant_id"],
                    "name": t.get("name", t["tenant_id"]),
                    "plan": plan,
                    "status": t.get("status", "Active"),
                    "daily_quota": plan_cfg["daily_quota"],
                    "allowed_operations": plan_cfg["allowed_operations"]
                }
        return None

    def set_status(self, tenant_id: str, status: str) -> bool:
        data = self._load()
        for t in data.get("tenants", []):
            if t["tenant_id"] == tenant_id:
                t["status"] = status
                self._save(data)
                return True
        return False

    def set_plan(self, tenant_id: str, plan: str) -> bool:
        data = self._load()
        for t in data.get("tenants", []):
            if t["tenant_id"] == tenant_id:
                t["plan"] = plan
                self._save(data)
                return True
        return False

def get_store() -> SubscriptionStore:
    if SUBSCRIPTION_STORE == "blob":
        try:
            from app.blob_subscriptions import BlobSubscriptionStore
            return BlobSubscriptionStore()
        except ImportError:
            return FileSubscriptionStore()
    return FileSubscriptionStore()

# Convenience module-level functions
def get_subscription(tenant_id: str) -> Optional[Dict[str, Any]]:
    return get_store().get_subscription(tenant_id)

def set_status(tenant_id: str, status: str) -> bool:
    return get_store().set_status(tenant_id, status)

def set_plan(tenant_id: str, plan: str) -> bool:
    return get_store().set_plan(tenant_id, plan)
