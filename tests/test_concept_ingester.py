import json
import os
import tempfile

import pytest

from hivemind.concept_ingester import ConceptIngester, extract_keywords, _fuzz, _token_overlap
from hivemind.hive_mind import HiveMind
from hivemind.config import load as load_config


@pytest.fixture
def hm():
    tmp = tempfile.mkdtemp()
    config = {
        "hives_dir": os.path.join(tmp, "hives"),
        "meta_graph_path": os.path.join(tmp, "meta.json"),
        "root": tmp,
    }
    os.makedirs(config["hives_dir"])
    hm = HiveMind(config)
    hm.create_hive("test-hive")
    yield hm
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestKeywordExtraction:
    def test_extract_simple(self):
        keywords = extract_keywords("We propose a novel Graph Neural Network architecture")
        assert "Graph Neural Network" in keywords

    def test_extract_acronym(self):
        keywords = extract_keywords("The GNN model achieves state-of-the-art results")
        assert any("GNN" in kw for kw in keywords)

    def test_extract_empty(self):
        assert extract_keywords("") == []

    def test_extract_ignores_stopwords(self):
        keywords = extract_keywords("a an the and or for with")
        # All stopwords — should return empty or very few
        assert len(keywords) == 0

    def test_extract_bigram(self):
        keywords = extract_keywords("We use Self-Attention in our Transformer model")
        assert any("Self-Attention" in kw for kw in keywords)

    def test_extract_deduplicates(self):
        keywords = extract_keywords("GNN GNN GNN")
        assert len(keywords) >= 1

    def test_extract_max_phrases(self):
        text = "A B C D E F G H I J K L M N O P" * 5
        keywords = extract_keywords(text, max_phrases=5)
        assert len(keywords) <= 5


class TestFuzzyMatch:
    def test_fuzz_identical(self):
        assert _fuzz("hello", "hello") == 1.0

    def test_fuzz_completely_different(self):
        assert _fuzz("abc", "xyz") < 0.5

    def test_token_overlap_identical(self):
        assert _token_overlap("graph neural network", "graph neural network") == 1.0

    def test_token_overlap_partial(self):
        score = _token_overlap("graph neural network", "neural network")
        assert 0 < score < 1.0

    def test_token_overlap_empty(self):
        assert _token_overlap("", "test") == 0.0
        assert _token_overlap("test", "") == 0.0


class TestIngest:
    def test_ingest_concept(self, hm):
        ci = ConceptIngester(hm)
        result = ci.ingest("Test Concept", hive="test-hive")
        assert result["status"] == "added"
        assert "Test Concept" in result["message"]

    def test_ingest_duplicate(self, hm):
        ci = ConceptIngester(hm)
        ci.ingest("Test Concept", hive="test-hive")
        result = ci.ingest("Test Concept", hive="test-hive")
        assert result["status"] == "skipped"

    def test_ingest_force_duplicate(self, hm):
        ci = ConceptIngester(hm)
        ci.ingest("Test Concept", hive="test-hive")
        result = ci.ingest("Test Concept", hive="test-hive", force=True)
        assert result["status"] == "added"

    def test_ingest_dry_run(self, hm):
        ci = ConceptIngester(hm)
        result = ci.ingest("Test Concept", hive="test-hive", dry_run=True)
        assert result["status"] == "dry_run"
        # verify it wasn't actually added
        kg = hm.get_hive_graph("test-hive")
        concepts = [n for n, d in kg.graph.nodes(data=True) if d.get("type") == "concept"]
        assert not any("Test Concept" in n for n in concepts)

    def test_ingest_no_hive(self, hm):
        ci = ConceptIngester(hm)
        result = ci.ingest("Some Random Concept")
        assert result["status"] in ("added", "error")  # may auto-suggest

    def test_ingest_from_text(self, hm):
        ci = ConceptIngester(hm)
        results = ci.ingest_from_text("We propose a Graph Neural Network architecture", hive="test-hive")
        assert len(results) >= 1
        statuses = {r["status"] for r in results}
        assert "added" in statuses or "skipped" in statuses

    def test_ingest_batch(self, hm):
        ci = ConceptIngester(hm)
        items = [
            {"keyword": "AlphaBatchConcept", "hive": "test-hive"},
            {"keyword": "BetaBatchConcept", "hive": "test-hive", "force": True},
        ]
        results = ci.ingest_batch(items)
        assert len(results) == 2
        assert all(r["status"] in ("added", "skipped") for r in results)

    def test_find_similar(self, hm):
        ci = ConceptIngester(hm)
        ci.ingest("Graph Neural Network", hive="test-hive")
        similar = ci.find_similar("graph neural", threshold=0.3)
        assert len(similar) >= 1
        assert similar[0]["label"] == "Graph Neural Network"

    def test_suggest_hive(self, hm):
        ci = ConceptIngester(hm)
        suggestions = ci.suggest_hive("test")
        assert len(suggestions) >= 1
        assert suggestions[0]["graph_id"] == "test-hive"

    def test_list_all_concepts(self, hm):
        ci = ConceptIngester(hm)
        ci.ingest("XyzAlphaConcept", hive="test-hive", force=True)
        ci.ingest("XyzBetaConcept", hive="test-hive", force=True)
        concepts = ci.list_all_concepts()
        assert len(concepts) >= 2

    def test_resolve_concept(self, hm):
        kg = hm.get_hive_graph("test-hive")
        kg.add_paper({
            "arxiv_id": "1706.03762",
            "title": "Attention Is All You Need",
            "authors": ["A"],
            "abstract": "The Transformer model uses self-attention.",
        })
        kg.save()
        ci = ConceptIngester(hm)
        cid = kg.add_concept("Self-Attention", "attention mechanism")
        links = ci.resolve_concept(cid, "Self-Attention", kg)
        assert len(links) >= 1
