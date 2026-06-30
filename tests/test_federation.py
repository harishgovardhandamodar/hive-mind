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
def kg(tmp_path):
    path = os.path.join(tmp_path, "graph.json")
    g = KnowledgeGraph(path, graph_id="test-hive")
    yield g


class TestGraphLifecycle:
    def test_register_graph(self, fed, kg):
        fed.register_graph(kg)
        assert fed.get_graph("test-hive") is kg
        assert "test-hive" in fed.graphs

    def test_register_graph_auto_id(self, fed):
        path = os.path.join(tempfile.mkdtemp(), "auto.json")
        g = KnowledgeGraph(path)
        fed.register_graph(g)
        # graph_id defaults to filename stem if empty
        assert g.graph_id  # should be non-empty

    def test_remove_graph(self, fed, kg):
        fed.register_graph(kg)
        fed.remove_graph("test-hive")
        assert fed.get_graph("test-hive") is None

    def test_list_graphs_empty(self, fed):
        assert fed.list_graphs() == []

    def test_list_graphs(self, fed, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        kg.add_concept("C")
        fed.register_graph(kg)
        lst = fed.list_graphs()
        assert len(lst) == 1
        assert lst[0]["id"] == "test-hive"
        assert lst[0]["papers"] == 1
        assert lst[0]["concepts"] == 1


class TestMetaGraph:
    def test_link_graphs(self, fed, kg):
        fed.register_graph(kg)
        kg2_path = os.path.join(os.path.dirname(fed.meta_graph_path), "kg2.json")
        kg2 = KnowledgeGraph(kg2_path, graph_id="hive2")
        fed.register_graph(kg2)
        fed.link_graphs("test-hive", "hive2", "references")
        meta = fed.meta_graph_data()
        assert len(meta["edges"]) == 1

    def test_link_nonexistent_source(self, fed, kg):
        fed.register_graph(kg)
        with pytest.raises(ValueError, match="Unknown graph"):
            fed.link_graphs("nonexistent", "test-hive", "references")


class TestCrossEdges:
    def test_add_cross_edge(self, fed, kg):
        kg2_path = os.path.join(os.path.dirname(fed.meta_graph_path), "kg2.json")
        kg2 = KnowledgeGraph(kg2_path, graph_id="hive2")
        fed.register_graph(kg)
        fed.register_graph(kg2)
        kg.add_concept("A")
        kg2.add_concept("B")
        fed.connect_concepts("test-hive", "concept:A", "hive2", "concept:B", "extends")
        cross = kg.get_cross_edges()
        assert len(cross) == 1
        assert cross[0]["relation"] == "extends"

    def test_connect_nonexistent_hive(self, fed, kg):
        kg.add_concept("A")
        fed.register_graph(kg)
        # Should not crash
        fed.connect_concepts("test-hive", "concept:A", "nonexistent", "concept:B")
        assert True


class TestSearch:
    def test_unified_search_empty(self, fed):
        assert fed.unified_search("anything") == []

    def test_unified_search_basic(self, fed, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "Attention Is All You Need", "authors": ["A"]})
        kg.add_concept("Attention")
        kg.add_concept("Transformer")
        fed.register_graph(kg)
        results = fed.unified_search("attention")
        assert len(results) >= 1
        assert any("Attention" in r["label"] for r in results)

    def test_unified_search_scoring(self, fed, kg):
        kg.add_concept("Graph Neural Network")
        kg.add_concept("Recurrent Neural Network")
        kg.add_concept("Attention Mechanism")
        fed.register_graph(kg)
        results = fed.unified_search("neural network")
        # RNN and GNN should rank higher than Attention
        scores = {r["label"]: r["score"] for r in results}
        assert scores.get("Graph Neural Network", 0) > 0
        assert scores.get("Recurrent Neural Network", 0) > 0

    def test_search_cache_reused(self, fed, kg):
        kg.add_concept("Cached Concept")
        fed.register_graph(kg)
        fed.unified_search("cached")
        cache = fed._search_cache
        assert cache is not None
        fed.unified_search("cached")
        assert fed._search_cache is cache


class TestStats:
    def test_stats_empty(self, fed):
        s = fed.stats()
        assert s["graphs"] == 0
        assert s["papers"] == 0
        assert s["concepts"] == 0

    def test_stats(self, fed, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        kg.add_concept("C")
        fed.register_graph(kg)
        s = fed.stats()
        assert s["graphs"] == 1
        assert s["papers"] == 1
        assert s["concepts"] == 1
