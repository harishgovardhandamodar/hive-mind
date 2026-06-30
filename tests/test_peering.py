import os
import tempfile
import time

import pytest

from hivemind.federation import Federation
from hivemind.knowledge_graph import KnowledgeGraph


@pytest.fixture
def fed():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "meta.json")
    f = Federation(path)
    yield f
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestPeering:
    def test_instance_info(self, fed):
        info = fed.instance_info()
        assert info["instance_id"]
        assert info["fingerprint"]
        assert info["hive_count"] == 0

    def test_set_instance_name_and_url(self, fed):
        fed.set_instance_name("Test Server")
        fed.set_public_url("https://example.com:9090")
        info = fed.instance_info()
        assert info["instance_name"] == "Test Server"
        assert info["url"] == "https://example.com:9090"
        assert info["tls"] is True

    def test_create_and_verify_invite(self, fed):
        invite = fed.create_invite(ttl=600)
        token = invite["token"]
        assert token
        assert fed.verify_invite(token) is True

    def test_verify_invite_rejects_replay(self, fed):
        token = fed.create_invite(ttl=600)["token"]
        assert fed.verify_invite(token) is True
        assert fed.verify_invite(token) is False

    def test_verify_invite_rejects_expired(self, fed):
        past = int(time.time()) - 10
        import hashlib
        import hmac
        import uuid
        token = str(uuid.uuid4())
        payload = f"{token}:{past}"
        sig = hmac.new(fed._instance_secret.encode(), payload.encode(),
                       hashlib.sha256).hexdigest()[:12]
        expired = f"{token}:{past}:{sig}"
        assert fed.verify_invite(expired) is False

    def test_add_list_remove_peer(self, fed):
        fed.set_public_url("http://local:9090")
        peer = fed.add_peer("http://remote:9090", "Remote")
        assert peer["url"] == "http://remote:9090"
        peers = fed.list_peers()
        assert len(peers) == 1
        fed.remove_peer(peer["id"])
        assert fed.list_peers() == []

    def test_add_self_raises(self, fed):
        fed.set_public_url("http://local:9090")
        with pytest.raises(ValueError, match="Cannot add self"):
            fed.add_peer("http://local:9090")

    def test_find_peer_by_url(self, fed):
        fed.set_public_url("http://local:9090")
        fed.add_peer("http://remote:9090", "Remote")
        found = fed.find_peer_by_url("http://remote:9090")
        assert found is not None
        assert found["name"] == "Remote"
