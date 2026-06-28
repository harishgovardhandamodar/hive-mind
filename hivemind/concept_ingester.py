import difflib
import os
import re
from collections import Counter
from typing import Any

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

    def find_similar(self, keyword: str, threshold: float = 0.5) -> list[dict[str, Any]]:
        kl = keyword.lower()
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

    def ingest(self, keyword: str, definition: str = "",
               hive: str | None = None, force: bool = False,
               relation: str = "related_to",
               connect_to: list[str] | None = None,
               dry_run: bool = False) -> dict[str, Any]:
        name = keyword.strip()
        if not name:
            return {"status": "error", "message": "Empty keyword"}

        similar = self.find_similar(name, threshold=0.7)
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

        similar_in_target = self.find_similar(name, threshold=0.7)
        similar_in_target = [m for m in similar_in_target if m["graph_id"] == target_hive]
        if similar_in_target and not force:
            return {
                "status": "skipped",
                "message": f"Similar concept already exists in hive '{target_hive}': "
                           f"'{similar_in_target[0]['label']}'",
                "similar": similar_in_target[:3],
                "added": None,
            }

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

        kg.save()
        return {
            "status": "added",
            "message": f"Concept '{name}' added to hive '{target_hive}'",
            "node_id": node_id,
            "hive": target_hive,
            "similar": similar[:3] if similar else [],
            "added": {"id": node_id, "label": name, "definition": definition},
        }

    def ingest_batch(self, items: list[dict[str, Any]],
                     default_hive: str | None = None,
                     force: bool = False) -> list[dict[str, Any]]:
        results = []
        for item in items:
            keyword = item.get("keyword", item.get("name", ""))
            definition = item.get("definition", item.get("def", ""))
            hive = item.get("hive", default_hive)
            connect_to = item.get("connect_to")
            result = self.ingest(keyword, definition, hive, force, connect_to=connect_to)
            results.append(result)
        return results

    def ingest_from_text(self, text: str, hive: str | None = None,
                         force: bool = False,
                         min_score: float = 0.3) -> list[dict[str, Any]]:
        keywords = extract_keywords(text)
        results = []
        for kw in keywords[:20]:
            result = self.ingest(kw, "", hive, force)
            results.append(result)
        return results

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
