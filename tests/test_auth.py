import json
import os
import tempfile

import pytest

from hivemind.auth import AccessControl


@pytest.fixture
def auth(tmp_path):
    perm_path = tmp_path / "permissions.json"
    perm_path.write_text(json.dumps({
        "admin1": {
            "name": "admin",
            "key": "admin-secret-key",
            "hives": {},
        },
        "reader1": {
            "name": "reader",
            "key": "reader-secret-key",
            "hives": {"hive-a": "read", "hive-b": "write"},
        },
    }))
    config = {
        "meta_graph_path": str(tmp_path / "meta.json"),
        "auth_path": str(perm_path),
    }
    return AccessControl(config)


class TestAccessControl:
    def test_authenticate_valid_key(self, auth):
        info = auth.authenticate("reader-secret-key")
        assert info is not None
        assert info["name"] == "reader"

    def test_authenticate_invalid_key(self, auth):
        assert auth.authenticate("wrong-key") is None

    def test_check_access_admin_all_hives(self, auth):
        info = auth.authenticate("admin-secret-key")
        assert auth.check_access(info, "any-hive", "admin") is True
        assert auth.check_access(info, "any-hive", "write") is True

    def test_check_access_read_role(self, auth):
        info = auth.authenticate("reader-secret-key")
        assert auth.check_access(info, "hive-a", "read") is True
        assert auth.check_access(info, "hive-a", "write") is False

    def test_check_access_write_role(self, auth):
        info = auth.authenticate("reader-secret-key")
        assert auth.check_access(info, "hive-b", "write") is True
        assert auth.check_access(info, "hive-b", "admin") is False

    def test_check_access_missing_hive(self, auth):
        info = auth.authenticate("reader-secret-key")
        assert auth.check_access(info, "unknown-hive", "read") is False

    def test_create_and_revoke_key(self, auth):
        created = auth.create_key("bot")
        assert created["key"]
        assert auth.authenticate(created["key"]) is not None
        assert auth.revoke_key(created["id"]) is True
        assert auth.authenticate(created["key"]) is None

    def test_grant_and_revoke_hive(self, auth):
        created = auth.create_key("limited")
        auth.grant(created["id"], "hive-x", "write")
        info = auth.authenticate(created["key"])
        assert auth.check_access(info, "hive-x", "write") is True
        auth.revoke(created["id"], "hive-x")
        info = auth.authenticate(created["key"])
        assert auth.check_access(info, "hive-x", "read") is False

    def test_grant_invalid_role(self, auth):
        assert auth.grant("reader1", "hive-a", "superuser") is False

    def test_list_keys_redacts_secrets(self, auth):
        keys = auth.list_keys()
        assert all("key" not in k for k in keys)
        assert len(keys) >= 2
