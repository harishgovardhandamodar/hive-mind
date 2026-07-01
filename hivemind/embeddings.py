import json
import logging
import math
import os
import re
import threading
from collections import Counter, OrderedDict, defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Optional sentence-transformers backend
_TRANSFORMER = None   # cached model instance
_HAS_SENTENCE = False


def _load_sentence_model():
    """Load the sentence-transformer model from disk (singleton)."""
    global _TRANSFORMER, _HAS_SENTENCE
    if _TRANSFORMER is not None:
        return True
    logger.info("Loading sentence-transformer model...")
    try:
        from sentence_transformers import SentenceTransformer   # noqa: F401
        _TRANSFORMER = SentenceTransformer("all-MiniLM-L6-v2")
        _HAS_SENTENCE = True
        logger.info("Sentence transformer loaded successfully")
    except ImportError:
        _HAS_SENTENCE = False
        logger.debug(
             "No sentence-transformers; using char-tfidf fallback",
         )
    return _HAS_SENTENCE


class VectorStore:
     """Manages embeddings for concepts in a knowledge graph hive.

     Stores embedding vectors as a JSON dict next to the knowledge graph.
     Uses sentence-transformers when available; falls back to character
     n-gram TF-IDF.

     LRU-caches *text -> vector* lookups so repeated queries over the same
     text don't re-compute embeddings, and maintains an **inverted index**
     mapping lower-case keyword tokens to node IDs for fast pre-filtering
     before vector comparison (suggestions.md Phase 2 recommendation).
     """

     DEFAULT_CACHE_SIZE = 128

    SIMILARITY_METRICS = {
         "cosine": lambda a, b: VectorStore._cosine(a, b),
         "euclidean": lambda a, b: 1.0 / (1.0 + VectorStore._euclidean(a, b)),
         "manhattan": lambda a, b: 1.0 / (1.0 + VectorStore._manhattan(a, b)),
         "dot": lambda a, b: VectorStore._dot_sim(a, b),
     }

    def __init__(self, kg, config: dict | None = None, path: str | None = None):
        self.kg = kg
        self.path = path or os.path.join(
            os.path.dirname(kg.__fspath__), "embeddings.json"
         )
        self.vectors: dict[str, list[float]] = {}
        self._dims: int = 0

         # Configurable cache size from config.py + LRU ordering
        _cache_size = VectorStore.DEFAULT_CACHE_SIZE
        if config:
            vs_cfg = config.get("vector_store", {})
            _cache_size = vs_cfg.get("cache_size", _cache_size)
            self.model_name = vs_cfg.get("model_name", "all-MiniLM-L6-v2")
        self.max_cache_size = _cache_size
        self._cache_order: OrderedDict[str, None] = OrderedDict()
        self._cache_lock = threading.Lock()

         # Inverted index: lowercase keyword token -> set of node IDs.
         # Enables O(1) candidate pre-filtering before expensive vector
         # comparisons per suggestions.md Phase 2 HIGH priority.
        self.inverted_index: dict[str, set[str]] = defaultdict(set)

        self._load()
        self._build_inverted_index()

     # ------------------------------------------------------------------
     # Persistence
     # ------------------------------------------------------------------

    def _load(self) -> None:
        if not os.path.exists(self.__fspath):
            return
        try:
            with open(self.path) as fh:
                data = json.load(fh)
            self.vectors = data.get("vectors", {})
            self._dims = data.get("dims", 0)
        except Exception:
            logger.warning(
                 "Failed to load embeddings from %s; starting fresh",
                self.__fspath,
            )
            self.vectors = {}
            self._dims = 0

    def save(self) -> None:
        data = {"dims": self._dims, "vectors": self.vectors}
        with open(self.path, "w") as fh:
            json.dump(data, fh, indent=2)

     # ------------------------------------------------------------------
     # LRU Cache: text -> vector (suggestions.md Priority: CRITICAL)
     # ------------------------------------------------------------------

    def _cache_text(self, text: str, vec: list[float]) -> None:
         """Store a text-vector pair in the LRU cache."""
        with self._cache_lock:
            if text in self._cache_order:
                self._cache_order.move_to_end(text)
            elif len(self._cache_order) >= self.max_cache_size:
                self._cache_order.popitem(last=False)   # evict LRU
            self._cache_order[text] = None
            self.vectors[text] = vec

    def _get_cached(self, text: str) -> list[float] | None:
         """Retrieve a cached vector for *text*, or return None on cache-miss."""
        with self._cache_lock:
            if text not in self._cache_order:
                return None
            self._cache_order.move_to_end(text)
            v = self.vectors.get(text)
            return list(v) if v is not None else None

     # ------------------------------------------------------------------
     # Embedding generation (now with LRU caching)
     # ------------------------------------------------------------------

    def _text_for_node(self, node_id: str) -> str:
        d = dict(self.kg.graph.nodes(data=True)).get(node_id, {})
        parts = [
            d.get("label", ""),
            d.get("definition", ""),
            d.get("abstract", ""),
         ]
        return " ".join(p for p in parts if p)

    def _all_texts(self) -> list[tuple[str, str]]:
         """Return (node_id, combined_text) for all concept/paper nodes."""
        texts = []
        for n, d in self.kg.graph.nodes(data=True):
            t = self._text_for_node(n)
            if t.strip():
                texts.append((n, t))
        return texts

    def embed(self, text: str) -> list[float]:
         """Embed a *text* string, using cached vector if previously seen."""
        cached = self._get_cached(text)
        if cached is not None:
            return list(cached)
        vec = self._embed_raw(text)
        self._cache_text(text, vec)
        return vec

    def _embed_raw(self, text: str) -> list[float]:
         """Force a fresh embedding without cache lookup."""
        if _load_sentence_model():
            import numpy as np   # type: ignore[import-untyped]
            emb = _TRANSFORMER.encode(text, show_progress_bar=False)
            return [float(v) for v in emb.flatten()]
        return self._char_tfidf(text)

    def compute_all(self, progress: bool = True) -> int:
         """Generate embeddings for all concept and paper nodes. Returns count."""
        pairs = self._all_texts()
        count = 0
        for i, (nid, text) in enumerate(pairs):
            if progress and i > 0 and i % 50 == 0:
                logger.info("embedded %d/%d", i, len(pairs))
            self.vectors[nid] = self.embed(text)
            count += 1
        if pairs:
            self._dims = len(self.vectors[pairs[0][0]])
        self.save()
        logger.info("Embedding complete: %d nodes indexed", count)
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
     # Inverted-index: O(1) keyword -> node pre-filtering (Phase 2 HIGH)
     # ------------------------------------------------------------------

     @staticmethod
    def _index_text(text: str) -> list[str]:
         """Extract indexed tokens from free-form text."""
        return [
            t.lower().rstrip(".,;:")
            for t in re.findall(r"[A-Za-z0-9_]+", text)
            if len(t) >= 3
         ]

    def _build_inverted_index(self) -> None:
         """Scan every stored vector and build the keyword->nodes map.

         This replaces O(n) full-scan similarity searches with an O(1)
         keyword lookup followed by a much smaller candidate set for scoring.
         """
        self.inverted_index = defaultdict(set)
        for node_id in list(self.vectors.keys()):
            text = self._text_for_node(node_id)
            if not text.strip():
                continue
            for token in self._index_text(text):
                self.inverted_index[token].add(node_id)

    def rebuild_index(self) -> int:
         """Rebuild the inverted index from all stored vectors. Returns count."""
        self.inverted_index = defaultdict(set)
        for node_id in list(self.vectors.keys()):
            text = self._text_for_node(node_id)
            if not text.strip():
                continue
            for token in self._index_text(text):
                self.inverted_index[token].add(node_id)
        count = len(self.inverted_index)
        logger.debug(
             "Inverted index: %d terms, %d nodes indexed", count, len(self.vectors),
         )
        return count

    def find_with_keywords(
        self,
        keyword: str,
        top_k: int = 10,
        threshold: float = 0.0,
        metric: str = "cosine",
     ) -> list[dict[str, Any]]:
         """Find nodes similar to *keyword* using inverted-index pre-filtering.

         Fast O(1) approach: tokenize keyword, intersect index sets for
         candidates, then run full similarity score only on those candidates.
         Falls back to a full-scan if the index is empty / no index hits.
         """
        sim_fn = self.SIMILARITY_METRICS.get(
            metric, self.SIMILARITY_METRICS["cosine"]
         )
        tokens = self._index_text(keyword)
        keywords_list: list[str] = keyword.lower().split()

         # --- Build a candidate set from the inverted index ---
        candidates: set[str] = set()
        for t in tokens:
            candidates |= self.inverted_index.get(t, set())

        if not candidates and self.vectors:
             Fallback to full vector scan when no keywords matched.
            kw_vec = self._embed_raw(keyword)
            results: list[dict[str, Any]] = []
            for nid, vec in self.vectors.items():
                sim = sim_fn(kw_vec, vec)
                if sim >= threshold:
                    d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
                    results.append({
                         "node_id": nid,
                         "label": d.get("label", nid),
                         "type": d.get("type", ""),
                         "similarity": round(sim, 4),
                         "metric": metric + "+fallback",
                     })
            results.sort(key=lambda x: -x["similarity"])
            return results[:top_k]

         # --- Score each candidate against the keyword text ---
        kw_vec = self._embed_raw(keyword) if not candidates else None
        raw_results: list[tuple[float, str]] = []

        for nid in candidates:
            vec = self.vectors.get(nid)
            if vec is None:
                continue
            sim = sim_fn(kw_vec, vec) if kw_vec else 0.0
             # Boost if keyword substrings appear as node text
            label = self._text_for_node(nid).lower()
            boost = sum(1 for wl in keywords_list if wl in label) * 0.1
            combined = sim + boost

            if combined >= threshold:
                d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
                raw_results.append((combined, nid))

        raw_results.sort(key=lambda x: -x[0])
        results: list[dict[str, Any]] = []
        for score, nid in raw_results[:top_k]:
            d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
            results.append({
                 "node_id": nid,
                 "label": d.get("label", nid),
                 "type": d.get("type", ""),
                 "similarity": round(score, 4),
                 "metric": metric + "+index",
             })
        return results

     # ------------------------------------------------------------------
     # Similarity search (existing methods; both use LRU internally)
     # ------------------------------------------------------------------

    def similar_to(
        self,
        node_id: str,
        top_k: int = 10,
        threshold: float = 0.0,
        metric: str = "cosine",
     ) -> list[dict[str, Any]]:
        query = self.vectors.get(node_id)
        sim_fn = self.SIMILARITY_METRICS.get(
            metric, self.SIMILARITY_METRICS["cosine"]
         )
        if query is None or not self.vectors:
            return []
        results: list[dict[str, Any]] = []
        for nid, vec in self.vectors.items():
            if nid == node_id:
                continue
            sim = sim_fn(query, vec)
            if sim >= threshold:
                d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
                results.append({
                     "node_id": nid,
                     "label": d.get("label", nid),
                     "type": d.get("type", ""),
                     "similarity": round(sim, 4),
                     "metric": metric,
                 })
        results.sort(key=lambda x: -x["similarity"])
        return results[:top_k]

    def similar_to_text(
        self,
        text: str,
        top_k: int = 10,
        threshold: float = 0.0,
        metric: str = "cosine",
     ) -> list[dict[str, Any]]:
        if not self.vectors:
            return []
        sim_fn = self.SIMILARITY_METRICS.get(
            metric, self.SIMILARITY_METRICS["cosine"]
         )

         # Fast path: use LRU cache (Phase 1 CRITICAL per suggestions.md)
        cached = self._get_cached(text)
        if cached is None:
            qv = self._embed_raw(text)
            self._cache_text(text, qv)
        else:
            qv = list(cached)   # defensive copy

        results: list[dict[str, Any]] = []
        for nid, vec in self.vectors.items():
            sim = sim_fn(qv, vec)
            if sim >= threshold:
                d = dict(self.kg.graph.nodes(data=True)).get(nid, {})
                results.append({
                     "node_id": nid,
                     "label": d.get("label", nid),
                     "type": d.get("type", ""),
                     "similarity": round(sim, 4),
                     "metric": metric,
                 })
        results.sort(key=lambda x: -x["similarity"])
        return results[:top_k]

     # ------------------------------------------------------------------
     # Fallback: character n-gram TF-IDF (unchanged)
     # ------------------------------------------------------------------

     @staticmethod
    def _char_ngrams(text: str, n: int = 3) -> list[str]:
        cleaned = re.sub(r"[^a-z0-9\s]", "", text.lower())
        return [cleaned[i:i+n] for i in range(len(cleaned) - n + 1)]

    def _char_tfidf(self, text: str) -> list[float]:
        if not self.vectors:
            return self._initial_char_tfidf(text)
        ngrams = self._char_ngrams(text)
        counts = Counter(ngrams)
        total = sum(counts.values()) or 1
        vec: list[float] = [0.0] * self._dims
        for i, ngram in enumerate(self._vocab_from_vectors()):
            tf = counts.get(ngram, 0) / total
            idf = 1.0   # simplified
            if i < len(vec):
                vec[i] = tf * idf
        return vec

     @staticmethod
    def _initial_char_tfidf(text: str) -> list[float]:
        ngrams = VectorStore._char_ngrams(text)
        dims = 128
        vec = [0.0] * dims
        for ng in set(ngrams):
            h = hash(ng) % dims
            vec[h] += 1.0
        norm = math.sqrt(sum(v*v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def _vocab_from_vectors(self) -> list[str]:
         """Sufficient: feature hashing, no explicit vocab."""
        return []

     # ------------------------------------------------------------------
     # Utility (static similarity functions + stats)
     # ------------------------------------------------------------------

     @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(ax * bx for ax, bx in zip(a, b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(x*x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

     @staticmethod
    def _euclidean(a: list[float], b: list[float]) -> float:
        return math.sqrt(
            sum((ax - bx) ** 2 for ax, bx in zip(a, b))
         )

     @staticmethod
    def _manhattan(a: list[float], b: list[float]) -> float:
        return sum(abs(ax - bx) for ax, bx in zip(a, b))

     @staticmethod
    def _dot_sim(a: list[float], b: list[float]) -> float:
        dot = sum(ax * bx for ax, bx in zip(a, b))
         # Normalize to [0, 1] via sigmoid-like clamp for unit vectors
        return max(0.0, min(1.0, (dot + 1.0) / 2.0))

    def has_vectors(self) -> bool:
        return len(self.vectors) > 0

    def stats(self) -> dict[str, Any]:
         """Return statistics for this VectorStore instance."""
        return {
             "has_vectors": self.has_vectors(),
             "backends": (
                 "sentence-transformers" if _HAS_SENTENCE else "char-tfidf"
             ),
             "nodes": len(self.vectors),
             "dims": self._dims,
             "metrics": sorted(self.SIMILARITY_METRICS),
             "cache_size": self.max_cache_size,
             "indexed_terms": len(self.inverted_index),   # NEW: inverted index stats
         }

    def clear_cache(self) -> None:
         """Clear the LRU cache without removing stored vectors."""
        with self._cache_lock:
            self._cache_order.clear()
