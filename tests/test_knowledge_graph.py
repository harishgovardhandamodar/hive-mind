import json
import os
import tempfile

import pytest

from hivemind.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "graph.json")
    g = KnowledgeGraph(path, graph_id="test-hive")
    yield g
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestNodes:
    def test_add_paper(self, kg):
        nid = kg.add_paper({
            "arxiv_id": "1706.03762",
            "title": "Attention Is All You Need",
            "authors": ["Vaswani et al."],
            "abstract": "The Transformer.",
        })
        assert nid == "paper:1706.03762"
        assert kg.graph.nodes[nid]["type"] == "paper"
        assert kg.graph.nodes[nid]["label"] == "Attention Is All You Need"

    def test_add_concept(self, kg):
        nid = kg.add_concept("Self-Attention", "Attention mechanism")
        assert nid == "concept:Self-Attention"
        assert kg.graph.nodes[nid]["type"] == "concept"
        assert kg.graph.nodes[nid]["definition"] == "Attention mechanism"

    def test_add_concept_normalizes_label(self, kg):
        nid = kg.add_concept("  Graph  Neural  Network  ")
        assert nid == "concept:Graph Neural Network"
        assert kg.graph.nodes[nid]["label"] == "Graph Neural Network"

    def test_add_concept_does_not_overwrite_definition(self, kg):
        kg.add_concept("Test", "original")
        kg.add_concept("Test", "new")
        assert kg.graph.nodes["concept:Test"]["definition"] == "original"

    def test_add_graph_ref(self, kg):
        nid = kg.add_graph_ref("other-hive", "Other Hive")
        assert nid == "graph_ref:other-hive"
        assert kg.graph.nodes[nid]["type"] == "graph_ref"

    def test_has_paper(self, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        assert kg.has_paper("1706.03762")
        assert not kg.has_paper("9999.99999")

    def test_has_any_paper_id(self, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        found = kg.has_any_paper_id(["1706.03762", "9999.99999"])
        assert found == {"1706.03762"}


class TestEdges:
    def test_add_edge(self, kg):
        kg.add_concept("A")
        kg.add_concept("B")
        kg.add_edge("concept:A", "concept:B", "related_to")
        assert kg.graph.has_edge("concept:A", "concept:B")

    def test_add_edge_validates_relation(self, kg):
        kg.add_concept("A")
        kg.add_concept("B")
        kg.add_edge("concept:A", "concept:B", "invalid_relation")
        assert kg.graph.edges["concept:A", "concept:B", 0]["relation"] == "related_to"

    def test_add_cross_edge(self, kg):
        kg.add_concept("A")
        kg.add_cross_edge("concept:A", "other-hive", "concept:B", "extends")
        edges = kg.get_cross_edges()
        assert len(edges) == 1
        assert edges[0]["target_graph"] == "other-hive"
        assert edges[0]["relation"] == "extends"


class TestQueries:
    def test_get_all_concepts(self, kg):
        kg.add_concept("A", "def a")
        kg.add_concept("B", "def b")
        concepts = kg.get_all_concepts()
        assert len(concepts) == 2
        assert any(c["name"] == "A" for c in concepts)
        assert any(c["name"] == "B" for c in concepts)

    def test_get_all_papers(self, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T1", "authors": ["A"]})
        kg.add_paper({"arxiv_id": "2006.16236", "title": "T2", "authors": ["B"]})
        papers = kg.get_all_papers()
        assert len(papers) == 2

    def test_get_papers_for_concept(self, kg):
        pid = kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        cid = kg.add_concept("Attention")
        kg.add_edge(pid, cid, "introduces")
        papers = kg.get_papers_for_concept("Attention")
        assert pid in papers

    def test_get_related_concepts(self, kg):
        c1 = kg.add_concept("A")
        c2 = kg.add_concept("B")
        kg.add_edge(c1, c2, "related_to")
        related = kg.get_related_concepts("A")
        assert "B" in related

    def test_find_similar_concept(self, kg):
        kg.add_concept("Graph Neural Network")
        match = kg.find_similar_concept("graph neural network", threshold=0.8)
        assert match == "Graph Neural Network"

    def test_find_similar_concept_no_match(self, kg):
        kg.add_concept("Attention")
        match = kg.find_similar_concept("Quantum Computing", threshold=0.5)
        assert match is None

    def test_stats(self, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        kg.add_concept("C1")
        kg.add_concept("C2")
        kg.add_graph_ref("other")
        s = kg.stats()
        assert s["papers"] == 1
        assert s["concepts"] == 2
        assert s["graph_refs"] == 1


class TestMerge:
    def test_merge_concepts(self, kg):
        kg.add_concept("A")
        kg.add_concept("B")
        kg.add_edge("concept:A", "concept:B", "related_to")
        kg.add_edge("concept:B", "concept:A", "related_to")
        kg.merge_concepts("A", "B")
        assert not kg.graph.has_node("concept:A")
        assert kg.graph.has_node("concept:B")
        assert kg.stats()["concepts"] == 1

    def test_merge_nonexistent(self, kg):
        kg.add_concept("B")
        kg.merge_concepts("A", "B")  # A doesn't exist — no crash
        assert kg.stats()["concepts"] == 1


class TestPersistence:
    def test_save_load_roundtrip(self, kg):
        kg.add_paper({"arxiv_id": "1706.03762", "title": "T", "authors": ["A"]})
        kg.add_concept("Test Concept", "A definition")
        kg.add_edge("paper:1706.03762", "concept:Test Concept", "introduces")
        kg.save()

        # Load into a new instance
        kg2 = KnowledgeGraph(kg.path, graph_id="test-hive")
        assert kg2.graph.has_node("paper:1706.03762")
        assert kg2.graph.has_node("concept:Test Concept")
        assert kg2.graph.has_edge("paper:1706.03762", "concept:Test Concept")
        assert kg2.graph.nodes["concept:Test Concept"]["definition"] == "A definition"

    def test_save_creates_backup(self, kg):
        kg.add_concept("Initial")
        kg.save()
        assert len(kg.list_backups()) == 0  # first save has nothing to back up

        kg.add_concept("Second")
        kg.save()
        backups = kg.list_backups()
        assert len(backups) >= 1  # second save backs up first

    def test_restore(self, kg):
        kg.add_concept("WillBeRemoved")
        kg.save()
        kg.graph.remove_node("concept:WillBeRemoved")
        kg.add_concept("NewConcept")
        kg.save()

        backups = kg.list_backups()
        assert len(backups) >= 1
        kg.restore(backups[-1]["version"])
        assert kg.graph.has_node("concept:WillBeRemoved")
        assert not kg.graph.has_node("concept:NewConcept")

    def test_get_backup_data_not_found(self, kg):
        assert kg.get_backup_data("nonexistent") is None

    def test_restore_invalid_version(self, kg):
        with pytest.raises(ValueError, match="not found"):
            kg.restore("nonexistent")
