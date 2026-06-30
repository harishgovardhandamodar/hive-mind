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


def _register_hive(fed, tmp_path, graph_id, concepts):
    path = os.path.join(tmp_path, f"{graph_id}.json")
    kg = KnowledgeGraph(path, graph_id=graph_id)
    for c in concepts:
        kg.add_concept(c)
    kg.save()
    fed.register_graph(kg)
    return kg


class TestLinkConcepts:
    def test_find_candidates(self, fed, tmp_path):
        _register_hive(fed, tmp_path, "gnns", ["Graph Neural Network"])
        _register_hive(fed, tmp_path, "ml", ["graph neural network"])
        candidates = fed.find_concept_link_candidates(threshold=0.85)
        assert len(candidates) == 1
        assert candidates[0]["score"] >= 0.85

    def test_dry_run_does_not_link(self, fed, tmp_path):
        _register_hive(fed, tmp_path, "a", ["Attention"])
        _register_hive(fed, tmp_path, "b", ["Attention"])
        result = fed.auto_link_concepts(threshold=0.85, dry_run=True)
        assert result["linked_count"] == 0
        kg_a = fed.get_graph("a")
        assert len(kg_a.get_cross_edges()) == 0

    def test_apply_creates_cross_edge(self, fed, tmp_path):
        _register_hive(fed, tmp_path, "a", ["Transformer"])
        _register_hive(fed, tmp_path, "b", ["Transformer"])
        result = fed.auto_link_concepts(threshold=0.85, dry_run=False)
        assert result["linked_count"] == 1
        kg_a = fed.get_graph("a")
        cross = kg_a.get_cross_edges()
        assert len(cross) == 1
        assert cross[0]["relation"] == "related_to"

    def test_skips_already_linked(self, fed, tmp_path):
        _register_hive(fed, tmp_path, "a", ["Embedding"])
        _register_hive(fed, tmp_path, "b", ["Embedding"])
        fed.auto_link_concepts(threshold=0.85, dry_run=False)
        second = fed.find_concept_link_candidates(threshold=0.85)
        assert second == []
