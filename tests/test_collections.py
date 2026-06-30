import os
import tempfile

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


@pytest.fixture
def hive(fed, tmp_path):
    path = os.path.join(tmp_path, "a.json")
    kg = KnowledgeGraph(path, graph_id="hive-a")
    kg.add_concept("Alpha")
    fed.register_graph(kg)
    return kg


class TestCollections:
    def test_create_and_list(self, fed):
        c = fed.create_collection("Research", "My research hives")
        assert c["id"] == "research"
        lst = fed.list_collections()
        assert len(lst) == 1
        assert lst[0]["name"] == "Research"

    def test_create_duplicate_raises(self, fed):
        fed.create_collection("Research")
        with pytest.raises(ValueError, match="already exists"):
            fed.create_collection("Research")

    def test_add_and_get_hive(self, fed, hive):
        fed.create_collection("Group")
        fed.add_hive_to_collection("group", "hive-a")
        detail = fed.get_collection("group")
        assert len(detail["hives"]) == 1
        assert detail["hives"][0]["id"] == "hive-a"

    def test_add_unknown_hive_raises(self, fed):
        fed.create_collection("Group")
        with pytest.raises(ValueError, match="Hive 'missing' not found"):
            fed.add_hive_to_collection("group", "missing")

    def test_remove_hive_from_collection(self, fed, hive):
        fed.create_collection("Group")
        fed.add_hive_to_collection("group", "hive-a")
        fed.remove_hive_from_collection("group", "hive-a")
        detail = fed.get_collection("group")
        assert detail["hives"] == []

    def test_delete_collection(self, fed):
        fed.create_collection("Temp")
        fed.delete_collection("temp")
        assert fed.list_collections() == []
