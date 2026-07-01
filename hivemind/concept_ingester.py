import difflib
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any

import requests

from .embeddings import VectorStore

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
     "global",       "multi", "cross", "intra", "inter",
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


def extract_keywords(text, min_len=3, max_phrases=30):
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.\-]+", text)
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
    words_in_phrases = set()
    for phrase, _ in candidates:
        parts = phrase.lower().split()
        if len(parts) > 1:
            words_in_phrases.update(parts)

     # add single-word candidates only if not part of a larger phrase
    for w, score in single_candidates:
        if w.lower() not in words_in_phrases:
            candidates.append((w, score * 0.85))

     # deduplicate by lowercased form, keep highest score
    seen = {}
    seen_score = {}
    for phrase, score in candidates:
        key = phrase.lower().strip("-.")
        if key not in seen_score or score > seen_score[key]:
            seen[key] = phrase
            seen_score[key] = score

     # sort by score descending, return top N
    scored = [(p, seen_score.get(p.lower().strip("-.") , 0)) for p in seen.values()]
    scored.sort(key=lambda x: (-x[1], -len(x[0])))
    return [p[0] for p in scored[:max_phrases]]


def _has_breaker(*words):
     """Return True if any word in the phrase is a breaker word."""
    lower = {w.lower() for w in words if w}
    return bool(lower & PHRASE_BREAKERS)


def _phrase_score(*words):
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


def _phrase_key(phrase, original_text):
    pl = phrase.lower()
    base = len(pl) * 0.05
    if pl in original_text.lower():
        base += 0.5
    if any(w[0].isupper() for w in pl.split()):
        base += 0.3
    return base


def _parse_arxiv_id(entry):
     """Extract arxiv ID from an Atom entry."""
    for link in entry.findall("a:link", {"a": "http://www.w3.org/2005/Atom"}):
        href = link.get("href", "")
        if "abs/" in href:
            return href.split("abs/")[-1].split("v")[0].strip("/")
    id_tag = entry.findtext("a:id", "", {"a": "http://www.w3.org/2005/Atom"})
    if "abs/" in id_tag:
        return id_tag.split("abs/")[-1].split("v")[0]
    return None


def _get_text(entry, path):
    text = entry.findtext(path, "") or ""
    return " ".join(text.split())


def _fuzz(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _token_overlap(a, b):
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


class ConceptIngester:
    def __init__(self, hive_mind):
        self.hm = hive_mind
        self.fed = hive_mind.federation

     # ------------------------------------------------------------------
     # Similarity search (vector + fuzzy/token with caching)
     # ------------------------------------------------------------------

    def find_similar(self, keyword, threshold=0.5,
                    use_vectors=True, metric="cosine"):
        kl = keyword.lower()

         # Try vector embedding search first (per-hive, now LRU-cached)
        if use_vectors:
            vec_matches = []
            for gid, kg in self.fed.graphs.items():
                vs = VectorStore(kg)
                if vs.has_vectors():
                      # Primary: cached text-based similarity search
                    results = vs.similar_to_text(keyword, top_k=5,
                                                 threshold=threshold * 0.6,
                                                 metric=metric)

                      # Secondary: use inverted index if available
                    if not results and vs.inverted_index:
                        results = vs.find_with_keywords(
                            keyword, top_k=5,
                            threshold=threshold * 0.6, metric=metric
                        )

                    for r in results:
                        vec_matches.append({
                             "score": round(r["similarity"] * 2, 3),    # scale to match fuzz scale
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

         # Fallback: fuzzy + token overlap (full-scan O(n))
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

    def suggest_hive(self, keyword):
        kl = keyword.lower()
        scores = {}

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

    def resolve_concept(self, node_id, name, kg, min_word_match=1):
         """Find papers in kg whose title/abstract mention name and link them."""
        name_lower = name.lower()
        key_tokens = {t for t in name_lower.split() if len(t) > 2 and t not in STOPWORDS}
        linked = []
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

    def ingest(self, keyword, definition="", hive=None, force=False,
               relation="related_to", connect_to=None, dry_run=False,
               resolve=True, metric="cosine"):
        name = keyword.strip()
        if not name:
            return {"status": "error", "message": "Empty keyword"}

         # Try vector-based search first (now with LRU caching)
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

         # Auto-embed the new concept (uses LRU cache now)
        try:
            vs = VectorStore(kg)
            if not vs.has_vectors():
                vs.compute_all()
            else:
                vs.embed_node(node_id)
                vs.rebuild_index()                  # keep index fresh
        except Exception:
             # embedding is best-effort

        kg.save()

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

    def ingest_batch(self, items, default_hive=None, force=False, metric="cosine"):
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

    def ingest_from_text(self, text, hive=None, force=False, min_score=0.3, metric="cosine"):
        keywords = extract_keywords(text)
        results = []
        for kw in keywords[:20]:
            result = self.ingest(kw, "", hive, force, metric=metric)
            results.append(result)
        return results

    def search_arxiv(self, query, hive_name=None, max_results=10,
                      max_concepts=10, resolve=True):
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

        NS = {"a": "http://www.w3.org/2005/Atom",
               "arxiv": "http://arxiv.org/schemas/atom"}

        try:
            url = f"https://export.arxiv.org/api/query?search_query=all:{requests.utils.quote(query)}&max_results={max_results}&start=0"
            r = requests.get(url, headers={"User-Agent": "HiveMind/1.0"}, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:
            return {"status": "error", "message": f"Arxiv search failed: {e}"}

        entries = root.findall("a:entry", NS)
        if not entries:
            return {"status": "ok", "message": f"No arxiv results for '{query}'",
                      "hive": target_hive, "papers_added": [], "concepts_added": []}

        for entry in entries:
            arxiv_id = _parse_arxiv_id(entry)
            if not arxiv_id or kg.has_paper(arxiv_id):
                continue

            title = _get_text(entry, "a:title")
            abstract = _get_text(entry, "a:summary")
            authors = [a.findtext("a:name", "", NS)
                       for a in entry.findall("a:author", NS)]
            published = _get_text(entry, "a:published")[:10]
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

            combined = f" {title} {abstract}"
            keywords = extract_keywords(combined, max_phrases=max_concepts)
            for kw in keywords[:max_concepts]:
                concept_node = kg.add_concept(kw, "")
                kg.add_edge(paper_node, concept_node, "introduces")
                if resolve:
                    self.resolve_concept(concept_node, kw, kg)

                 # Auto-rebuild vector index as concepts get added
                try:
                    vs = VectorStore(kg)
                    vs.rebuild_index()
                except Exception:
                    pass

            time.sleep(0.3)

        kg.save()

         # Rebuild inverted index after all hives are updated
         for _kg in self.fed.graphs.values():
            try:
                VectorStore(_kg).rebuild_index()
            except Exception:
                pass

        return {
             "status": "ok",
             "message": f"Imported {len(papers_added)} papers, {len(set(concepts_added))} concepts into '{target_hive}'",
             "hive": target_hive,
             "papers_added": papers_added,
             "concepts_added": list(set(concepts_added)),
         }

    def import_from_arxiv(self, arxiv_ids, hive_name=None, max_concepts=10, resolve=True):
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

        ARXIV_URL = "https://export.arxiv.org/api/query?id_list="
        NS = {"a": "http://www.w3.org/2005/Atom",
               "arxiv": "http://arxiv.org/schemas/atom"}

        for i in range(0, len(arxiv_ids), 50):
            batch = arxiv_ids[i:i+50]
            try:
                r = requests.get(ARXIV_URL + ",".join(batch),
                                 headers={"User-Agent": "HiveMind/1.0"},
                                 timeout=15)
                r.raise_for_status()
                root = ET.fromstring(r.content)
            except Exception as e:
                return {"status": "error", "message": f"Arxiv fetch failed: {e}"}

            for entry in root.findall("a:entry", NS):
                arxiv_id = _parse_arxiv_id(entry)
                if not arxiv_id or kg.has_paper(arxiv_id):
                    continue

                title = _get_text(entry, "a:title")
                abstract = _get_text(entry, "a:summary")
                authors = [a.findtext("a:name", "", NS)
                           for a in entry.findall("a:author", NS)]
                published = _get_text(entry, "a:published")[:10]
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

                 # extract concepts from title + abstract
                combined = f" {title} {abstract}"
                keywords = extract_keywords(combined, max_phrases=max_concepts)
                for kw in keywords[:max_concepts]:
                    concept_node = kg.add_concept(kw, "")
                    kg.add_edge(paper_node, concept_node, "introduces")
                    if resolve:
                        self.resolve_concept(concept_node, kw, kg)

                 # Rebuild index incrementally for performance
                    try:
                        VectorStore(kg).rebuild_index()
                    except Exception:
                        pass

                 # Throttle arxiv API
                time.sleep(0.3)

        kg.save()

         # Final batch rebuild across all hives
        for _kg in self.fed.graphs.values():
            try:
                VectorStore(_kg).rebuild_index()
            except Exception:
                pass

        return {
             "status": "ok",
             "message": f"Imported {len(papers_added)} papers, {len(concepts_added)} concepts into '{target_hive}'",
             "hive": target_hive,
             "papers_added": papers_added,
             "concepts_added": list(set(concepts_added)),
         }

    def _link_across_hives(self, node_id, name, source_hive, threshold=0.65, metric="cosine"):
        links = []
        for gid, kg in self.fed.graphs.items():
            if gid == source_hive:
                continue
             # Try vector search first (with inverted index pre-filter if available)
            vs = VectorStore(kg)
            results = []
            if vs.has_vectors():
                  if vs.inverted_index:                       # Use index to pre-filter candidates
                    candidates = {n for n, d in kg.graph.nodes(data=True)
                                  if d.get("type") == "concept"}
                    idx_terms  = set(vs.index_text(name))
                    if idx_terms:
                        candidates &= set()   # start fresh; not actually needed with index
                    results = vs.similar_to_text(name, top_k=3,
                                                 threshold=threshold * 0.6, metric=metric)
                     # Also try inverted-index fast path for speed
                    if not results:
                        results = vs.find_with_keywords(
                            name, top_k=3,
                            threshold=threshold * 0.6, metric=metric
                        )
                else:
                      # Fallback without index: fuzzy/token overlap
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

    def list_all_concepts(self):
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

    def rebuild_all_indexes(self):
         """Rebuild the inverted index for every hive vector store."""
        results = {}
        for gid, kg in self.fed.graphs.items():
            try:
                vs = VectorStore(kg)
                count = vs.rebuild_index()
                results[gid] = {"indexed_terms": count}
            except Exception as e:
                results[gid] = {"error": str(e)}
        return results
