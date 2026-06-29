import json
import math
import os
import re
import time
from collections import Counter
from typing import Any

# Optional sentence-transformers backend
_TRANSFORMER = None  # cached model instance
_HAS_SENTENCE = False

def _load_sentence_model():
    global _TRANSFORMER, _HAS_SENTENCE
    if _TRANSFORMER is not None:
        return True
    try:
        from sentence_transformers import SentenceTransformer
        _TRANSFORMER = SentenceTransformer("all-MiniLM-L6-v2")
        _HAS_SENTENCE = True
        return True
    except ImportError:
        _HAS_SENTENCE = False
        return False


class VectorStore:
    """Manages embeddings for concepts in a knowledge graph hive.

    Stores embedding vectors as a JSON dict next to the knowledge graph.
    Uses sentence-transformers when available; falls back to character n-gram TF-IDF.
    """

    def __init__(self, kg, path: str | None = None):
        self.kg = kg
        self.path = path or os.path.join(os.path.dirname(kg.path), "embeddings.json")
        self.vectors: dict[str, list[float]] = {}
        self._dims = 0
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path) as f:
                    data = json.load(f)
                self.vectors = data.get("vectors", {})
                self._dims = data.get("dims", 0)
            except Exception:
                self.vectors = {}
                self._dims = 0

    def save(self) -> None:
        data = {"dims": self._dims, "vectors": self.vectors}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Embedding generation
    # ------------------------------------------------------------------

    def _text_for_node(self, node_id: str) -> str:
        d = dict(self.kg.graph.nodes(data=True)).get(node_id, {})
        parts = [d.get("label", ""), d.get("definition", ""), d.get("abstract", "")]
        return " ".join(p for p in parts if p)

    def _all_texts(self) -> list[tuple[str, str]]:
        """Return (node_id, text) for all concept and paper nodes."""
        texts = []
        for n, d in self.kg.graph.nodes(data=True):
            t = self._text_for_node(n)
            if t.strip():
                texts.append((n, t))
        return texts

    def embed(self, text: str) -> list[float]:
        if _load_sentence_model():
            emb = _TRANSFORMER.encode(text, show_progress_bar=False)
            return emb.tolist()
        return self._char_tfidf(text)

    def compute_all(self, progress: bool = True) -> int:
        """Generate embeddings for all concept and paper nodes. Returns count."""
        pairs = self._all_texts()
        count = 0
        for i, (nid, text) in enumerate(pairs):
            if progress and i > 0 and i % 50 == 0:
                print(f"  embedded {i}/{len(pairs)}")
            self.vectors[nid] = self.embed(text)
            count += 1
        self._dims = len(self.vectors[pairs[0][0]]) if pairs else 0
        self.save()
        return count

    def embed_node(self, node_id: str) -> bool:
        text = self._text_for_node(node_id)
        if not text.strip():
            return False
        self.vectors[node_id] = self.embed(text)
        self._dims = len(self.vectors[node_id])
        self.save()
        return True

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def similar_to(self, node_id: str, top_k: int = 10,
                   threshold: float = 0.0) -> list[dict[str, Any]]:
        query = self.vectors.get(node_id)
        if query is None or not self.vectors:
            return []
        results = []
        for nid, vec in self.vectors.items():
            if nid == node_id:
                continue
            sim = self._cosine(query, vec)
            if sim >= threshold:
                d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
                results.append({
                    "node_id": nid,
                    "label": d.get("label", nid),
                    "type": d.get("type", ""),
                    "similarity": round(sim, 4),
                })
        results.sort(key=lambda x: -x["similarity"])
        return results[:top_k]

    def similar_to_text(self, text: str, top_k: int = 10,
                        threshold: float = 0.0) -> list[dict[str, Any]]:
        if not self.vectors:
            return []
        qv = self.embed(text)
        results = []
        for nid, vec in self.vectors.items():
            sim = self._cosine(qv, vec)
            if sim >= threshold:
                d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
                results.append({
                    "node_id": nid,
                    "label": d.get("label", nid),
                    "type": d.get("type", ""),
                    "similarity": round(sim, 4),
                })
        results.sort(key=lambda x: -x["similarity"])
        return results[:top_k]

    # ------------------------------------------------------------------
    # Fallback: character n-gram TF-IDF
    # ------------------------------------------------------------------

    def _char_ngrams(self, text: str, n: int = 3) -> list[str]:
        cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
        return [cleaned[i:i+n] for i in range(len(cleaned) - n + 1)]

    def _char_tfidf(self, text: str) -> list[float]:
        if not self.vectors:
            return self._initial_char_tfidf(text)
        ngrams = self._char_ngrams(text)
        counts = Counter(ngrams)
        total = sum(counts.values()) or 1
        # Use global IDF from stored vectors if available
        vec = [0.0] * self._dims
        for i, ngram in enumerate(self._vocab_from_vectors()):
            tf = counts.get(ngram, 0) / total
            idf = 1.0  # simplified
            if i < len(vec):
                vec[i] = tf * idf
        return vec

    def _initial_char_tfidf(self, text: str) -> list[float]:
        ngrams = self._char_ngrams(text)
        # Fixed dimension using feature hashing
        dims = 128
        vec = [0.0] * dims
        for ng in set(ngrams):
            h = hash(ng) % dims
            vec[h] += 1.0
        norm = math.sqrt(sum(v*v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _vocab_from_vectors(self) -> list[str]:
        # Simplified: use feature hashing, no explicit vocab
        return []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(ax * bx for ax, bx in zip(a, b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(x*x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def has_vectors(self) -> bool:
        return len(self.vectors) > 0

    def stats(self) -> dict[str, Any]:
        return {
            "has_vectors": self.has_vectors(),
            "backends": "sentence-transformers" if _HAS_SENTENCE else "char-tfidf",
            "nodes": len(self.vectors),
            "dims": self._dims,
        }
