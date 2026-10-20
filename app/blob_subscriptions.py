import json
import os
from typing import Any, Dict, Optional
from azure.storage.blob import BlobServiceClient
from app.subscriptions import SubscriptionStore, PLAN_CONFIGS

BLOB_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "subscriptions")
BLOB_NAME = os.getenv("AZURE_STORAGE_BLOB_NAME", "subscriptions.json")

class BlobSubscriptionStore(SubscriptionStore):
    def __init__(self, connection_string: Optional[str] = None, container_name: Optional[str] = None):
        self.conn_str = connection_string or BLOB_CONNECTION_STRING
        self.container_name = container_name or CONTAINER_NAME
        self.blob_name = BLOB_NAME

    def _get_blob_client(self):
        if not self.conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not configured.")
        service_client = BlobServiceClient.from_connection_string(self.conn_str)
        return service_client.get_blob_client(container=self.container_name, blob=self.blob_name)

    def _load(self) -> Dict[str, Any]:
        try:
            blob_client = self._get_blob_client()
            download_stream = blob_client.download_blob()
            data = json.loads(download_stream.readall().decode("utf-8"))
            return data
        except Exception:
            # Fallback to seed.json if blob not found or container empty
            base_dir = os.path.dirname(os.path.dirname(__file__))
            seed_path = os.path.join(base_dir, "seed.json")
            if os.path.exists(seed_path):
                with open(seed_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            return {"tenants": []}

    def _save(self, data: Dict[str, Any]) -> None:
        blob_client = self._get_blob_client()
        content = json.dumps(data, indent=2).encode("utf-8")
        blob_client.upload_blob(content, overwrite=True)

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
