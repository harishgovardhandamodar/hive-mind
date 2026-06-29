import json
import logging
import os
import secrets
from typing import Any

logger = logging.getLogger(__name__)

ROLES = ("read", "write", "admin")


class AccessControl:
    """Simple API-key-based access control.

    Stores a permissions file alongside the meta-graph.
    Each key has a name, key, and a mapping of hive → role.
    """

    def __init__(self, config: dict):
        self.path = config.get("auth_path",
                               os.path.join(os.path.dirname(config.get("meta_graph_path", "")),
                                            "permissions.json"))
        self._permissions: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    self._permissions = json.load(f)
            except Exception:
                self._permissions = {}
        else:
            # Create default admin key if no permissions file exists
            default_key = secrets.token_hex(16)
            self._permissions = {
                "default": {
                    "name": "default-admin",
                    "key": default_key,
                    "hives": {},  # empty = all hives admin
                }
            }
            self._save()
            logger.warning("Default admin key created: %s", default_key)
            logger.warning("Store this key safely — it will not be shown again.")

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self._permissions, f, indent=2)

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def create_key(self, name: str) -> dict[str, Any]:
        kid = secrets.token_hex(8)
        key = secrets.token_hex(24)
        self._permissions[kid] = {
            "name": name,
            "key": key,
            "hives": {},
        }
        self._save()
        return {"id": kid, "name": name, "key": key}

    def list_keys(self) -> list[dict[str, Any]]:
        return [
            {
                "id": kid,
                "name": info.get("name", ""),
                "hives": info.get("hives", {}),
            }
            for kid, info in self._permissions.items()
        ]

    def revoke_key(self, key_id: str) -> bool:
        if key_id in self._permissions:
            del self._permissions[key_id]
            self._save()
            return True
        return False

    # ------------------------------------------------------------------
    # Grant / revoke hive access
    # ------------------------------------------------------------------

    def grant(self, key_id: str, hive: str, role: str = "read") -> bool:
        if key_id not in self._permissions:
            return False
        if role not in ROLES:
            return False
        self._permissions[key_id].setdefault("hives", {})[hive] = role
        self._save()
        return True

    def revoke(self, key_id: str, hive: str) -> bool:
        if key_id not in self._permissions:
            return False
        self._permissions[key_id].get("hives", {}).pop(hive, None)
        self._save()
        return True

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self, key: str) -> dict[str, Any] | None:
        """Return the key info if valid, or None."""
        for kid, info in self._permissions.items():
            if info.get("key") == key:
                return {"id": kid, "name": info.get("name", ""), "hives": info.get("hives", {})}
        return None

    def check_access(self, key_info: dict[str, Any] | None,
                     hive: str, required_role: str = "read") -> bool:
        """Check if a key has the required role for a hive.

        Empty hives dict = admin access to all hives.
        """
        if not key_info:
            return False
        hives = key_info.get("hives", {})
        if not hives:
            return True  # default admin key
        role = hives.get(hive, "")
        if not role:
            return False
        return ROLES.index(role) >= ROLES.index(required_role)

    def stats(self) -> dict[str, Any]:
        return {
            "keys": len(self._permissions),
            "path": self.path,
            "exists": os.path.exists(self.path),
        }
