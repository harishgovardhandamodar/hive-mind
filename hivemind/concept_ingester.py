import difflib
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import nullcontext
from typing import Any

import requests

from .embeddings import VectorStore

logger = logging.getLogger(__name__)

def _ollama_url() -> str:
    return os.getenv("OLLAMA_URL", "http://localhost:11434")


def _ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "gemma4:31b-mlx")


def _ollama_timeout() -> int:
    return int(os.getenv("OLLAMA_TIMEOUT", "30"))


def _ollama_enabled() -> bool:
    return os.getenv("USE_OLLAMA_DEFINITIONS", "false").lower() == "true"


def _get_definition_from_ollama(concept: str) -> str:
    if not _ollama_enabled():
        return ""
    prompt = (
        f"Provide a concise definition (2-3 sentences) for the term '{concept}'."
    )
    try:
        resp = requests.post(
            f"{_ollama_url()}/api/generate",
            json={"model": _ollama_model(), "prompt": prompt, "stream": False},
            timeout=_ollama_timeout(),
        )
        resp.raise_for_status()
        result = resp.json()
        text = (result.get("response") or "").strip()
        if 20 <= len(text) <= 500:
            return text
    except Exception as e:
        logger.warning("Ollama definition failed for '%s': %s", concept, e)
    return ""


def _fallback_keywords(text: str, max_concepts: int = 10) -> list[dict[str, str]]:
    return [{"concept": kw, "definition": ""}
            for kw in extract_keywords(text, max_phrases=max_concepts)[:max_concepts]]


def _extract_concepts_from_ollama(text: str, max_concepts: int = 10) -> list[dict[str, str]]:
    """Send abstract text to Ollama, parse returned concept-definition pairs.
    Falls back to heuristic keyword extraction (without definitions) if Ollama is unavailable."""
    if not _ollama_enabled():
        return _fallback_keywords(text, max_concepts)
    prompt = (
        "You are a research assistant analyzing an academic paper abstract. "
        "Extract the key technical concepts mentioned. "
        "For each concept, provide a concise definition (2-3 sentences).\n\n"
        f"Abstract:\n{text}\n\n"
        "Return ONLY a JSON array of objects with keys 'concept' and 'definition'. "
        f"Maximum {max_concepts} concepts. Example:\n"
        '[{"concept": "Graph Neural Network", "definition": "A neural network that operates on graph structures."}]'
    )
    try:
        resp = requests.post(
            f"{_ollama_url()}/api/generate",
            json={"model": _ollama_model(), "prompt": prompt, "stream": False},
            timeout=_ollama_timeout(),
        )
        resp.raise_for_status()
        result = resp.json()
        raw = (result.get("response") or "").strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        if not isinstance(data, list):
            logger.warning("Ollama concepts: expected list, got %s", type(data).__name__)
            return _fallback_keywords(text, max_concepts)
        out = []
        for item in data[:max_concepts]:
            concept = (item.get("concept") or "").strip()
            definition = (item.get("definition") or "").strip()
            if concept and len(concept) >= 3 and definition and 20 <= len(definition) <= 500:
                out.append({"concept": concept, "definition": definition})
        if out:
            return out
        logger.warning("Ollama returned no valid concepts, falling back to keyword extraction")
    except Exception as e:
        logger.warning("Ollama concept extraction failed: %s", e)
    return _fallback_keywords(text, max_concepts)

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "need",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "we", "our", "you", "your", "he", "she", "him", "her", "his", "who",
    "which", "what", "where", "when", "why", "how", "all", "each", "every",
    "both", "few", "more", "most", "some", "any", "no", "not", "only",
    "very", "just", "about", "than", "also", "well", "even", "still",
    "already", "however", "although", "because", "since", "while", "if",
    "then", "else", "so", "thus", "hence", "here", "there", "into", "onto",
    "upon", "within", "without", "through", "between", "among", "over",
    "under", "above", "below", "new", "based", "using", "via", "such",
    "use", "approach", "method", "methods", "technique", "techniques",
    "system", "model", "models", "data", "results",
    "large", "high", "low", "different", "multiple", "various", "important",
    "significant", "efficient", "effective", "novel", "new",
    "propose", "proposed", "proposes", "proposing",
    "introduce", "introduces", "introduced", "introducing",
    "present", "presents", "presented",
    "describe", "describes", "described",
    "develop", "develops", "developed",
    "enable", "enables", "enabled",
    "achieve", "achieves", "achieved",
    "demonstrate", "demonstrates", "demonstrated",
}

# Words that disqualify a phrase if present (pronouns, determiners, prepositions)
PHRASE_BREAKERS = {
    "a", "an", "the", "this", "that", "these", "those", "we", "our",
    "you", "your", "he", "she", "it", "its", "they", "them", "their",
    "which", "what", "where", "when", "why", "how", "who", "whom",
    "if", "then", "else", "so", "thus", "hence", "here", "there",
    "into", "onto", "upon", "within", "without", "through", "between",
    "among", "over", "under", "above", "below",
    "for", "nor", "but", "yet", "after", "before", "against",
    "during", "about", "across", "along", "around", "behind",
    "down", "near", "off", "out", "toward", "towards", "via",
    "while", "because", "although", "unless", "until",
    "not", "no", "none", "never",
    "novel", "new", "efficient", "effective", "robust", "scalable",
    "fast", "quick", "simple", "complex", "optimal", "adaptive",
    "large", "small", "big", "tiny", "high", "low", "deep", "wide",
    "flat", "hierarchical", "distributed", "centralized", "local",
    "global",     "multi", "cross", "intra", "inter",
    "propose", "proposed", "proposes", "proposing",
    "introduce", "introduces", "introduced", "introducing",
    "present", "presents", "presented",
    "describe", "describes", "described",
    "develop", "develops", "developed", "developing",
    "enable", "enables", "enabled", "enabling",
    "use", "uses", "used", "using",
    "achieve", "achieves", "achieved",
    "demonstrate", "demonstrates", "demonstrated",
    "called", "known", "termed", "named", "referred",
    "including", "includes", "included",
    "like", "such",
}


def extract_keywords(text: str, min_len: int = 3, max_phrases: int = 30) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]+", text)
    candidates = []

    # single words (only if not part of a larger phrase later)
    single_candidates = []
    for w in words:
        wl = w.lower()
        if len(wl) >= min_len and wl not in STOPWORDS and not wl.isdigit():
            is_acronym = len(wl) >= 2 and w.isupper()
            has_inner_upper = any(c.isupper() for c in w[1:])
            if is_acronym and len(wl) <= 8:
                single_candidates.append((w, 0.8))
            elif has_inner_upper and len(wl) >= 4:
                single_candidates.append((w, 0.7))

    # bigrams
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i+1]}"
        if len(bigram) >= min_len and not _has_breaker(*words[i:i+2]):
            score = _phrase_score(words[i], words[i+1])
            if score > 0:
                candidates.append((bigram, score))

    # trigrams
    for i in range(len(words) - 2):
        trigram = f"{words[i]} {words[i+1]} {words[i+2]}"
        if len(trigram) >= min_len and not _has_breaker(*words[i:i+3]):
            score = _phrase_score(words[i], words[i+1], words[i+2])
            if score >= 0.5:
                candidates.append((trigram, score * 0.9))

    # track which individual words appear in multi-word phrases
    words_in_phrases: set[str] = set()
    for phrase, _ in candidates:
        parts = phrase.lower().split()
        if len(parts) > 1:
            words_in_phrases.update(parts)

    # add single-word candidates only if not part of a larger phrase
    for w, score in single_candidates:
        if w.lower() not in words_in_phrases:
            candidates.append((w, score * 0.85))

    # deduplicate by lowercased form, keep highest score
    seen: dict[str, str] = {}
    seen_score: dict[str, float] = {}
    for phrase, score in candidates:
        key = phrase.lower().strip("-.")
        if key not in seen_score or score > seen_score[key]:
            seen[key] = phrase
            seen_score[key] = score

    # sort by score descending, return top N
    scored = [(p, seen_score.get(p.lower().strip("-."), 0)) for p in seen.values()]
    scored.sort(key=lambda x: (-x[1], -len(x[0])))
    return [p[0] for p in scored[:max_phrases]]


def _has_breaker(*words: str) -> bool:
    """Return True if any word in the phrase is a breaker word."""
    lower = {w.lower() for w in words if w}
    return bool(lower & PHRASE_BREAKERS)


def _phrase_score(*words: str) -> float:
    score = 0.0
    lower = [w.lower() for w in words]
    has_upper = any(w[0].isupper() for w in words if w)
    score += 0.4 if has_upper else -0.2
    non_stop = sum(1 for w in lower if w not in STOPWORDS)
    score += 0.2 * (non_stop / len(words)) - 0.1
    # penalty for trailing stopword
    if lower[-1] in STOPWORDS:
        score -= 0.3
    # bonus for all words being capitalized (proper noun phrase)
    if has_upper and all(w[0].isupper() for w in words if w and w[0].isalpha()):
        score += 0.2
    return max(score, 0.0)


def _phrase_key(phrase: str, original_text: str) -> float:
    pl = phrase.lower()
    base = len(pl) * 0.05
    if pl in original_text.lower():
        base += 0.5
    if any(w[0].isupper() for w in pl.split()):
        base += 0.3
    return base


def _parse_arxiv_id(entry) -> str | None:
    """Extract arxiv ID from an Atom entry."""
    for link in entry.findall("a:link", {"a": "http://www.w3.org/2005/Atom"}):
        href = link.get("href", "")
        if "abs/" in href:
            return href.split("abs/")[-1].split("v")[0].strip("/")
    id_tag = entry.findtext("a:id", "", {"a": "http://www.w3.org/2005/Atom"})
    if "abs/" in id_tag:
        return id_tag.split("abs/")[-1].split("v")[0]
    return None


def _get_text(entry, path: str, ns: dict) -> str:
    text = entry.findtext(path, "", ns) or ""
    return " ".join(text.split())


def _fuzz(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token_overlap(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


class ConceptIngester:
    def __init__(self, hive_mind):
        self.hm = hive_mind
        self.fed = hive_mind.federation

    def find_similar(self, keyword: str, threshold: float = 0.5,
                     use_vectors: bool = True,
                     metric: str = "cosine") -> list[dict[str, Any]]:
        kl = keyword.lower()

        # Try vector embedding search first (per-hive)
        if use_vectors:
            vec_matches = []
            for gid, kg in self.fed.graphs.items():
                vs = VectorStore(kg)
                if vs.has_vectors():
                    results = vs.similar_to_text(keyword, top_k=5, threshold=threshold * 0.6, metric=metric)
                    for r in results:
                        vec_matches.append({
                            "score": round(r["similarity"] * 2, 3),  # scale to match fuzz scale
                            "fuzz": 0,
                            "token_overlap": 0,
                            "graph_id": gid,
                            "node_id": r["node_id"],
                            "label": r["label"],
                            "definition": dict(kg.graph.nodes(data=True)).get(r["node_id"], {}).get("definition", ""),
                            "vector_score": r["similarity"],
                        })
            if vec_matches:
                vec_matches.sort(key=lambda x: -x["score"])
                return vec_matches[:10]

        # Fallback: fuzzy + token overlap
        matches = []
        for gid, kg in self.fed.graphs.items():
            for node, data in kg.graph.nodes(data=True):
                if data.get("type") != "concept":
                    continue
                label = data.get("label", "")
                fuzz_score = _fuzz(kl, label.lower())
                token_score = _token_overlap(kl, label.lower())
                overlap_score = max(fuzz_score, token_score)
                if overlap_score >= threshold:
                    matches.append({
                        "score": round(overlap_score, 3),
                        "fuzz": round(fuzz_score, 3),
                        "token_overlap": round(token_score, 3),
                        "graph_id": gid,
                        "node_id": node,
                        "label": label,
                        "definition": data.get("definition", ""),
                    })
        matches.sort(key=lambda x: -x["score"])
        return matches

    def suggest_hive(self, keyword: str) -> list[dict[str, Any]]:
        kl = keyword.lower()
        scores: dict[str, float] = {}

        for gid, kg in self.fed.graphs.items():
            score = 0.0
            display = gid.replace("-", " ")
            token_match = _token_overlap(kl, display)
            if token_match > 0:
                score += token_match * 3.0
            if display in kl or kl in display:
                score += 2.0

            for node, data in kg.graph.nodes(data=True):
                if data.get("type") != "concept":
                    continue
                label = data.get("label", "").lower()
                if label == kl:
                    score += 5.0
                elif kl in label or label in kl:
                    score += 1.5
                else:
                    score += _fuzz(kl, label) * 0.5

            if score > 0:
                scores[gid] = score

        sorted_hives = sorted(scores.items(), key=lambda x: -x[1])
        return [
            {
                "graph_id": gid,
                "score": round(score, 2),
                "existing_concept": any(
                    data.get("type") == "concept"
                    and data.get("label", "").lower() == kl
                    for _, data in self.fed.graphs[gid].graph.nodes(data=True)
                ),
            }
            for gid, score in sorted_hives[:5]
        ]

    def resolve_concept(self, node_id: str, name: str, kg,
                         min_word_match: int = 1) -> list[str]:
        """Find papers in kg whose title/abstract mention name and link them."""
        name_lower = name.lower()
        key_tokens = {t for t in name_lower.split() if len(t) > 2 and t not in STOPWORDS}
        linked: list[str] = []
        for n, data in kg.graph.nodes(data=True):
            if data.get("type") != "paper":
                continue
            haystack = f"{data.get('label', '')} {data.get('abstract', '')}".lower()
            # exact phrase match
            if name_lower in haystack:
                kg.add_edge(n, node_id, "related_to")
                linked.append(n)
                continue
            # token overlap match
            if key_tokens:
                paper_tokens = {t for t in haystack.split() if len(t) > 2}
                overlap = len(key_tokens & paper_tokens)
                if overlap >= min_word_match and overlap / len(key_tokens) >= 0.5:
                    kg.add_edge(n, node_id, "related_to")
                    linked.append(n)
        return linked

    def ingest(self, keyword: str, definition: str = "",
               hive: str | None = None, force: bool = False,
               relation: str = "related_to",
               connect_to: list[str] | None = None,
               dry_run: bool = False,
               resolve: bool = True,
               metric: str = "cosine") -> dict[str, Any]:
        name = keyword.strip()
        if not name:
            return {"status": "error", "message": "Empty keyword"}

        similar = self.find_similar(name, threshold=0.7, metric=metric)
        if similar and not force:
            return {
                "status": "skipped",
                "message": f"Similar concept already exists: '{similar[0]['label']}' "
                           f"in hive '{similar[0]['graph_id']}' (score={similar[0]['score']})",
                "similar": similar[:3],
                "added": None,
            }

        # determine target hive
        target_hive = hive
        if not target_hive:
            suggestions = self.suggest_hive(name)
            target_hive = suggestions[0]["graph_id"] if suggestions else None
        if not target_hive:
            return {"status": "error", "message": "No suitable hive found. Specify --hive."}

        kg = self.fed.get_graph(target_hive)
        if not kg:
            return {"status": "error", "message": f"Hive '{target_hive}' not found"}

        similar_in_target = self.find_similar(name, threshold=0.7, metric=metric)
        similar_in_target = [m for m in similar_in_target if m["graph_id"] == target_hive]
        if similar_in_target and not force:
            return {
                "status": "skipped",
                "message": f"Similar concept already exists in hive '{target_hive}': "
                           f"'{similar_in_target[0]['label']}'",
                "similar": similar_in_target[:3],
                "added": None,
            }

        if not definition and _ollama_enabled():
            definition = _get_definition_from_ollama(name)

        if dry_run:
            return {
                "status": "dry_run",
                "message": f"Would add '{name}' to hive '{target_hive}'",
                "node_id": None,
                "hive": target_hive,
                "similar": similar[:3] if similar else [],
                "added": {"id": f"concept:{name}", "label": name, "definition": definition},
            }

        node_id = kg.add_concept(name, definition)
        if connect_to:
            for target_name in connect_to:
                if kg.graph.has_node(f"concept:{target_name}"):
                    kg.add_edge(node_id, f"concept:{target_name}", relation)
                else:
                    tgt_sim = self.find_similar(target_name, threshold=0.5)
                    if tgt_sim:
                        for m in tgt_sim:
                            if m["graph_id"] == target_hive:
                                kg.add_edge(node_id, m["node_id"], relation)
                                break

        paper_links = []
        if resolve:
            paper_links = self.resolve_concept(node_id, name, kg)

        # Auto-embed the new concept
        try:
            vs = VectorStore(kg)
            if not vs.has_vectors():
                vs.compute_all()
            else:
                vs.embed_node(node_id)
        except Exception:
            pass  # embedding is best-effort

        kg.save()
        self.fed._invalidate_search_cache()

        # Cross-hive linking (auto-connect similar concepts in other hives)
        cross_links = self._link_across_hives(node_id, name, target_hive,
                                               metric=metric)

        return {
            "status": "added",
            "message": f"Concept '{name}' added to hive '{target_hive}'",
            "node_id": node_id,
            "hive": target_hive,
            "similar": similar[:3] if similar else [],
            "added": {"id": node_id, "label": name, "definition": definition},
            "paper_links": paper_links,
            "cross_links": cross_links,
        }

    def ingest_batch(self, items: list[dict[str, Any]],
                     default_hive: str | None = None,
                     force: bool = False,
                     metric: str = "cosine") -> list[dict[str, Any]]:
        results = []
        for item in items:
            keyword = item.get("keyword", item.get("name", ""))
            definition = item.get("definition", item.get("def", ""))
            hive = item.get("hive", default_hive)
            connect_to = item.get("connect_to")
            result = self.ingest(keyword, definition, hive, force, connect_to=connect_to,
                                 metric=metric)
            results.append(result)
        return results

    def ingest_from_text(self, text: str, hive: str | None = None,
                         force: bool = False,
                         min_score: float = 0.3,
                         metric: str = "cosine") -> list[dict[str, Any]]:
        keywords = extract_keywords(text)
        results = []
        kg = self.fed.get_graph(hive) if hive else None
        ctx = kg.batch() if kg else nullcontext()
        with ctx:
            for kw in keywords[:20]:
                result = self.ingest(kw, "", hive, force, metric=metric)
                results.append(result)
        if kg:
            self.fed._invalidate_search_cache()
        return results

    def search_arxiv(self, query: str, hive_name: str | None = None,
                      max_results: int = 10,
                      max_concepts: int = 10,
                      resolve: bool = True) -> dict[str, Any]:
        """Search arxiv by query, fetch matching papers, add to a hive."""
        if not query:
            return {"status": "error", "message": "No search query provided"}

        target_hive = hive_name
        if not target_hive:
            target_hive = query.lower().replace(" ", "-")[:30]
        if not self.fed.get_graph(target_hive):
            self.hm.create_hive(target_hive)

        kg = self.fed.get_graph(target_hive)
        papers_added = []
        concepts_added = []

        ARXIV_URL = "https://export.arxiv.org/api/query?search_query=all:{}&max_results={}&start=0"
        NS = {"a": "http://www.w3.org/2005/Atom",
              "arxiv": "http://arxiv.org/schemas/atom"}

        try:
            url = ARXIV_URL.format(requests.utils.quote(query), max_results)
            r = requests.get(url, headers={"User-Agent": "HiveMind/1.0"}, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            return {"status": "error", "message": f"Arxiv search failed: {e}"}

        entries = root.findall("a:entry", NS)
        if not entries:
            return {"status": "ok", "message": f"No arxiv results for '{query}'",
                    "hive": target_hive, "papers_added": [], "concepts_added": []}

        with kg.batch():
            for entry in entries:
                arxiv_id = _parse_arxiv_id(entry)
                if not arxiv_id or kg.has_paper(arxiv_id):
                    continue

                title = _get_text(entry, "a:title", NS)
                abstract = _get_text(entry, "a:summary", NS)
                authors = [a.findtext("a:name", "", NS)
                           for a in entry.findall("a:author", NS)]
                published = _get_text(entry, "a:published", NS)[:10]
                categories = [c.get("term", "") for c in entry.findall("a:category", NS)]

                paper_data = {
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "published": published,
                    "abstract": abstract,
                    "categories": categories,
                }
                paper_node = kg.add_paper(paper_data)
                papers_added.append(arxiv_id)

                combined = f"{title}\n{abstract}"
                concepts = _extract_concepts_from_ollama(combined, max_concepts)
                for c in concepts:
                    concept_node = kg.add_concept(c["concept"], c["definition"])
                    kg.add_edge(paper_node, concept_node, "introduces")
                    concepts_added.append(c["concept"])
                    if resolve:
                        self.resolve_concept(concept_node, c["concept"], kg)

                time.sleep(0.3)

        self.fed._invalidate_search_cache()
        return {
            "status": "ok",
            "message": f"Fetched {len(papers_added)} papers, {len(set(concepts_added))} concepts into '{target_hive}'",
            "hive": target_hive,
            "papers_added": papers_added,
            "concepts_added": list(set(concepts_added)),
        }

    def import_from_arxiv(self, arxiv_ids: list[str],
                          hive_name: str | None = None,
                          max_concepts: int = 10,
                          resolve: bool = True) -> dict[str, Any]:
        """Fetch papers from arxiv by IDs, add them to a hive, extract concepts."""
        if not arxiv_ids:
            return {"status": "error", "message": "No arxiv IDs provided"}

        # determine target hive
        target_hive = hive_name
        if not target_hive:
            # use first paper's category to determine hive
            target_hive = "imported"
        if not self.fed.get_graph(target_hive):
            self.hm.create_hive(target_hive)

        kg = self.fed.get_graph(target_hive)
        papers_added = []
        concepts_added = []

        ARXIV_URL = "https://export.arxiv.org/api/query?id_list={}"
        NS = {"a": "http://www.w3.org/2005/Atom",
              "arxiv": "http://arxiv.org/schemas/atom"}

        for i in range(0, len(arxiv_ids), 50):
            batch = arxiv_ids[i:i+50]
            try:
                r = requests.get(ARXIV_URL.format(",".join(batch)),
                                 headers={"User-Agent": "HiveMind/1.0"},
                                 timeout=15)
                r.raise_for_status()
                root = ET.fromstring(r.content)
            except Exception as e:
                return {"status": "error", "message": f"Arxiv fetch failed: {e}"}

            with kg.batch():
                for entry in root.findall("a:entry", NS):
                    arxiv_id = _parse_arxiv_id(entry)
                    if not arxiv_id or kg.has_paper(arxiv_id):
                        continue

                    title = _get_text(entry, "a:title", NS)
                    abstract = _get_text(entry, "a:summary", NS)
                    authors = [a.findtext("a:name", "", NS)
                               for a in entry.findall("a:author", NS)]
                    published = _get_text(entry, "a:published", NS)[:10]
                    categories = [c.get("term", "") for c in entry.findall("a:category", NS)]

                    paper_data = {
                        "arxiv_id": arxiv_id,
                        "title": title,
                        "authors": authors,
                        "published": published,
                        "abstract": abstract,
                        "categories": categories,
                    }
                    paper_node = kg.add_paper(paper_data)
                    papers_added.append(arxiv_id)

                    combined = f"{title}\n{abstract}"
                    concepts = _extract_concepts_from_ollama(combined, max_concepts)
                    for c in concepts:
                        concept_node = kg.add_concept(c["concept"], c["definition"])
                        kg.add_edge(paper_node, concept_node, "introduces")
                        concepts_added.append(c["concept"])
                        if resolve:
                            self.resolve_concept(concept_node, c["concept"], kg)

                    time.sleep(0.3)

        self.fed._invalidate_search_cache()
        return {
            "status": "ok",
            "message": f"Imported {len(papers_added)} papers, {len(concepts_added)} concepts into '{target_hive}'",
            "hive": target_hive,
            "papers_added": papers_added,
            "concepts_added": list(set(concepts_added)),
        }

    def _link_across_hives(self, node_id: str, name: str,
                            source_hive: str,
                            threshold: float = 0.65,
                            metric: str = "cosine") -> list[dict[str, Any]]:
        links = []
        for gid, kg in self.fed.graphs.items():
            if gid == source_hive:
                continue
            # Try vector search first
            vs = VectorStore(kg)
            if vs.has_vectors():
                results = vs.similar_to_text(name, top_k=3, threshold=threshold * 0.6, metric=metric)
            else:
                results = []
            # Fallback: fuzzy/token overlap
            if not results:
                for n, data in kg.graph.nodes(data=True):
                    if data.get("type") != "concept":
                        continue
                    label = data.get("label", "")
                    fuzz_score = _fuzz(name, label.lower())
                    token_score = _token_overlap(name, label.lower())
                    if max(fuzz_score, token_score) >= threshold:
                        results.append({
                            "node_id": n,
                            "label": label,
                            "similarity": max(fuzz_score, token_score),
                        })
            for match in results:
                target_label = match.get("label", match.get("node_id", ""))
                # Ensure we pass a plain concept name, not a prefixed node_id
                if target_label.startswith("concept:"):
                    target_label = target_label[len("concept:"):]
                self.fed.connect_concepts(
                    source_hive, name,
                    gid, target_label,
                    "related_to",
                )
                links.append({
                    "hive": gid,
                    "node_id": match.get("node_id"),
                    "label": match.get("label"),
                    "similarity": round(match.get("similarity", 1.0), 3),
                })
        return links

    def list_all_concepts(self) -> list[dict[str, Any]]:
        concepts = []
        for gid, kg in self.fed.graphs.items():
            for node, data in kg.graph.nodes(data=True):
                if data.get("type") == "concept":
                    concepts.append({
                        "graph_id": gid,
                        "node_id": node,
                        "label": data.get("label", ""),
                        "definition": data.get("definition", ""),
                    })
        return concepts

    def enrich_concept_definitions(self, hive: str | None = None,
                                    force: bool = False) -> dict[str, Any]:
        updated = 0
        skipped = 0
        errors = 0

        graphs = {hive: self.fed.get_graph(hive)} if hive else self.fed.graphs

        for gid, kg in graphs.items():
            if kg is None:
                continue
            for node, data in dict(kg.graph.nodes(data=True)).items():
                if data.get("type") != "concept":
                    continue
                name = data.get("label", "")
                existing = data.get("definition", "")
                if existing and not force:
                    skipped += 1
                    continue
                defn = _get_definition_from_ollama(name)
                if defn:
                    kg.graph.nodes[node]["definition"] = defn
                    updated += 1
                else:
                    errors += 1
            kg.save()

        self.fed._invalidate_search_cache()
        return {
            "status": "ok",
            "hive": hive or "all",
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
        }
