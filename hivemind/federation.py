import hashlib
import hmac
import json
import math
import os
import re
import time
import uuid
from collections import Counter
from typing import Any
from urllib.parse import urljoin
from urllib.request import urlopen, Request

import networkx as nx

from .knowledge_graph import KnowledgeGraph


class Federation:
    """Manages multiple KnowledgeGraphs, providing cross-graph linking
    and unified queries across all graphs in the federation."""

    def __init__(self, meta_graph_path: str, max_backups: int = 20):
        self.meta_graph_path = meta_graph_path
        self.max_backups = max_backups
        self.graphs: dict[str, KnowledgeGraph] = {}
        self.meta_graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.collections: dict[str, dict[str, Any]] = {}
        self._peers: dict[str, dict[str, Any]] = {}
        self._search_cache: dict[str, Any] | None = None
        self._search_cache_key: tuple | None = None
        self._load_meta()
        self._load_collections()
        self._load_peers()

    # ------------------------------------------------------------------
    # Graph lifecycle
    # ------------------------------------------------------------------

    def register_graph(self, graph: KnowledgeGraph,
                       owner: str = "") -> None:
        gid = graph.graph_id or os.path.splitext(os.path.basename(graph.path))[0]
        graph.graph_id = gid
        self.graphs[gid] = graph
        self._sync_meta_node(graph, owner)

    def create_graph(self, graph_id: str, storage_path: str,
                     owner: str = "") -> KnowledgeGraph:
        kg = KnowledgeGraph(storage_path, graph_id=graph_id, max_backups=self.max_backups)
        self.register_graph(kg, owner)
        return kg

    def load_graph(self, storage_path: str, graph_id: str = "") -> KnowledgeGraph:
        kg = KnowledgeGraph(storage_path, graph_id=graph_id, max_backups=self.max_backups)
        self.register_graph(kg)
        return kg

    def remove_graph(self, graph_id: str) -> None:
        self.graphs.pop(graph_id, None)
        if self.meta_graph.has_node(graph_id):
            self.meta_graph.remove_node(graph_id)
        self._invalidate_search_cache()
        self._save_meta()

    def get_graph(self, graph_id: str) -> KnowledgeGraph | None:
        return self.graphs.get(graph_id)

    def list_graphs(self) -> list[dict[str, Any]]:
        result = []
        for gid, kg in self.graphs.items():
            s = kg.stats()
            meta = self.meta_graph.nodes[gid] if self.meta_graph.has_node(gid) else {}
            visible = meta.get("visible", True)
            owner = meta.get("owner", "")
            result.append({
                "id": gid,
                "path": kg.path,
                "papers": s["papers"],
                "concepts": s["concepts"],
                "graph_refs": s["graph_refs"],
                "relations": s["relations"],
                "cross_edges": s["cross_edges"],
                "visible": visible,
                "owner": owner,
            })
        return result

    # ------------------------------------------------------------------
    # Cross-graph linking
    # ------------------------------------------------------------------

    def link_graphs(self, source_id: str, target_id: str,
                    relation: str = "references",
                    label: str = "") -> None:
        """Create a cross-graph reference edge in both meta-graph and source graph."""
        src_kg = self.graphs.get(source_id)
        tgt_kg = self.graphs.get(target_id)
        if not src_kg or not tgt_kg:
            raise ValueError(f"Unknown graph: {source_id if not src_kg else target_id}")

        src_kg.add_graph_ref(target_id, label or target_id, relation)
        src_kg.add_edge(f"graph_ref:{target_id}", target_id, relation)

        self.meta_graph.add_edge(source_id, target_id,
                                 relation=relation, label=label or relation)
        self._save_meta()
        src_kg.save()

    def add_cross_edge(self, source_graph: str, source_node: str,
                       target_graph: str, target_node: str,
                       relation: str = "related_to") -> None:
        src_kg = self.graphs.get(source_graph)
        if not src_kg:
            raise ValueError(f"Unknown source graph: {source_graph}")
        src_kg.add_cross_edge(source_node, target_graph, target_node, relation)
        src_kg.save()
        self._invalidate_search_cache()

    def connect_concepts(self, source_graph: str, concept_a: str,
                         target_graph: str, concept_b: str,
                         relation: str = "related_to") -> None:
        source_node = f"concept:{concept_a}"
        target_node = f"concept:{concept_b}"
        self.add_cross_edge(source_graph, source_node,
                            target_graph, target_node, relation)

    # ------------------------------------------------------------------
    # Cross-hive concept linking
    # ------------------------------------------------------------------

    @staticmethod
    def _label_similarity(label_a: str, label_b: str) -> float:
        a = label_a.lower().strip()
        b = label_b.lower().strip()
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    def _has_cross_concept_link(self, graph_a: str, node_a: str,
                                graph_b: str, node_b: str) -> bool:
        kg = self.graphs.get(graph_a)
        if not kg:
            return False
        target = f"{graph_b}:{node_b}"
        for u, v, d in kg.graph.edges(data=True):
            if d.get("cross_graph") and u == node_a and v == target:
                return True
        kg_b = self.graphs.get(graph_b)
        if not kg_b:
            return False
        target_rev = f"{graph_a}:{node_a}"
        for u, v, d in kg_b.graph.edges(data=True):
            if d.get("cross_graph") and u == node_b and v == target_rev:
                return True
        return False

    def find_concept_link_candidates(self, threshold: float = 0.85,
                                     limit: int = 100) -> list[dict[str, Any]]:
        """Find similar concepts across different hives above *threshold*."""
        candidates: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str]] = set()
        gids = list(self.graphs.keys())

        for i, gid_a in enumerate(gids):
            kg_a = self.graphs[gid_a]
            concepts_a = [
                (n, d.get("label", ""))
                for n, d in kg_a.graph.nodes(data=True)
                if d.get("type") == "concept" and d.get("label")
            ]
            for gid_b in gids[i + 1:]:
                kg_b = self.graphs[gid_b]
                for nb, db in kg_b.graph.nodes(data=True):
                    if db.get("type") != "concept":
                        continue
                    label_b = db.get("label", "")
                    if not label_b:
                        continue
                    for na, label_a in concepts_a:
                        score = self._label_similarity(label_a, label_b)
                        if score < threshold:
                            continue
                        key = (gid_a, na, gid_b, nb)
                        rev = (gid_b, nb, gid_a, na)
                        if key in seen or rev in seen:
                            continue
                        if self._has_cross_concept_link(gid_a, na, gid_b, nb):
                            continue
                        seen.add(key)
                        candidates.append({
                            "graph_a": gid_a,
                            "concept_a": label_a,
                            "node_a": na,
                            "graph_b": gid_b,
                            "concept_b": label_b,
                            "node_b": nb,
                            "score": round(score, 4),
                            "already_linked": False,
                        })

        candidates.sort(key=lambda x: -x["score"])
        return candidates[:limit]

    def auto_link_concepts(self, threshold: float = 0.85,
                           dry_run: bool = False,
                           limit: int = 100,
                           relation: str = "related_to") -> dict[str, Any]:
        candidates = self.find_concept_link_candidates(threshold, limit)
        linked: list[dict[str, Any]] = []
        if not dry_run:
            for c in candidates:
                self.connect_concepts(
                    c["graph_a"], c["concept_a"],
                    c["graph_b"], c["concept_b"],
                    relation=relation,
                )
                linked.append(c)
        return {
            "dry_run": dry_run,
            "threshold": threshold,
            "candidates": candidates,
            "linked_count": len(linked) if not dry_run else 0,
            "linked": linked,
        }

    # ------------------------------------------------------------------
    # Unified queries
    # ------------------------------------------------------------------

    def _search_fingerprint(self) -> tuple:
        return tuple(
            (gid, kg.graph.number_of_nodes(), kg.graph.number_of_edges())
            for gid, kg in sorted(self.graphs.items())
        )

    def _invalidate_search_cache(self) -> None:
        self._search_cache = None
        self._search_cache_key = None

    def _build_search_cache(self) -> None:
        docs: list[tuple[str, str, str, str, str, str]] = []
        for gid, kg in self.graphs.items():
            for node, data in kg.graph.nodes(data=True):
                label = data.get("label", "")
                defn = data.get("definition", "")
                text = f"{label} {defn}".lower()
                docs.append((gid, node, label, data.get("type", "unknown"), defn, text))

        N = len(docs)
        df: dict[str, int] = Counter()
        doc_vectors: list[Counter] = []
        for _, _, _, _, _, text in docs:
            tokens = self._tokenize(text)
            doc_vectors.append(Counter(tokens))
            for t in set(tokens):
                df[t] += 1

        self._search_cache = {"docs": docs, "N": N, "df": df, "doc_vectors": doc_vectors}
        self._search_cache_key = self._search_fingerprint()

    def unified_search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower().strip()
        if not q:
            return []

        # tokenize query
        q_tokens = self._tokenize(q)
        if not q_tokens:
            return []

        if self._search_cache is None or self._search_cache_key != self._search_fingerprint():
            self._build_search_cache()

        cache = self._search_cache
        docs = cache["docs"]
        N = cache["N"]
        df = cache["df"]
        doc_vectors = cache["doc_vectors"]

        # score each doc by query token TF–IDF
        scored: list[tuple[float, tuple[str, str, str, str, str]]] = []
        for i, (gid, node, label, typ, defn, text) in enumerate(docs):
            score = 0.0
            tv = doc_vectors[i]
            for qt in q_tokens:
                if qt in tv:
                    tf = tv[qt] / max(tv.values(), default=1)
                    idf = math.log((N + 1) / (df.get(qt, 0) + 1)) + 1
                    score += tf * idf
            # bonus for exact label / substring match
            if q in label.lower() or q in node.lower():
                score += 1.0
            if score > 0:
                scored.append((score, (gid, node, label, typ, defn)))

        scored.sort(key=lambda x: -x[0])
        return [
            {
                "graph_id": gid,
                "node_id": node,
                "label": label,
                "type": typ,
                "definition": defn,
                "score": round(s, 4),
            }
            for s, (gid, node, label, typ, defn) in scored[:50]
        ]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        words = re.findall(r"[A-Za-z0-9_.-]+", text.lower())
        stopwords = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
            "this", "that", "it", "its", "they", "them", "we", "our", "you",
            "which", "what", "where", "when", "why", "how", "who", "not", "no",
            "all", "each", "every", "both", "some", "any", "more", "most",
        }
        return [w for w in words if w not in stopwords and len(w) > 1]

    def get_all_nodes(self) -> list[dict[str, Any]]:
        nodes = []
        for gid, kg in self.graphs.items():
            for node, data in kg.graph.nodes(data=True):
                nodes.append({
                    "graph_id": gid,
                    "node_id": node,
                    "label": data.get("label", node),
                    "type": data.get("type", "unknown"),
                })
        return nodes

    def get_all_edges(self) -> list[dict[str, Any]]:
        edges = []
        for gid, kg in self.graphs.items():
            for u, v, data in kg.graph.edges(data=True):
                edges.append({
                    "source_graph": gid,
                    "target_graph": data.get("target_graph", gid),
                    "source": f"{gid}:{u}",
                    "target": f"{data.get('target_graph', gid)}:{v}",
                    "relation": data.get("relation", "related_to"),
                })
        return edges

    def query_relation(self, text: str) -> dict[str, Any]:
        q = text.lower()

        hive_names = {gid: gid.replace("-", " ") for gid in self.graphs}
        mentioned = []
        for gid, display in sorted(hive_names.items(), key=lambda x: -len(x[1])):
            if display in q or gid.lower() in q:
                mentioned.append(gid)
            else:
                base = re.split(r'[\(\[]', gid, maxsplit=1)[0].strip().lower()
                if base and base != gid.lower() and base in q:
                    mentioned.append(gid)

        # deduplicate but preserve order
        seen_mention: set[str] = set()
        mentioned_uniq = []
        for m in mentioned:
            if m not in seen_mention:
                seen_mention.add(m)
                mentioned_uniq.append(m)
        mentioned = mentioned_uniq

        if len(mentioned) < 2:
            return {"nodes": [], "edges": [],
                    "explanation": "Mention two hives, e.g. 'How is Photonic computing related to AI acceleration?'"}

        # If 3+ hives mentioned, use them as waypoints; else find meta-graph path
        if len(mentioned) >= 3:
            hive_chain = mentioned
        else:
            hive_chain = self._meta_path(mentioned[0], mentioned[1])

        node_set: dict[str, dict] = {}
        edge_list: list[dict] = []
        seen_edges_set: set[tuple[str, str, str]] = set()
        node_id_set: set[str] = set()

        def add_node(nid: str, data: dict, gid: str) -> None:
            if nid not in node_id_set:
                node_id_set.add(nid)
                node_set[nid] = {
                    "id": nid,
                    "label": data.get("label", nid),
                    "type": data.get("type", "unknown"),
                    "definition": data.get("definition", ""),
                    "graph_id": gid,
                }

        def add_edge_uniq(src: str, tgt: str, rel: str,
                          cross: bool = False, tgt_g: str = "") -> None:
            key = (src, tgt, rel)
            if key not in seen_edges_set:
                seen_edges_set.add(key)
                edge_list.append({
                    "source": src, "target": tgt, "relation": rel,
                    "cross_graph": cross, "target_graph": tgt_g,
                })

        # Collect cross edges for each consecutive pair in the chain
        chain_set = set(hive_chain)
        for gid in chain_set:
            kg = self.graphs[gid]
            for u, v, d in kg.graph.edges(data=True):
                tgg = d.get("target_graph")
                if d.get("cross_graph") and tgg in chain_set:
                    add_node(u, kg.graph.nodes[u], gid) if kg.graph.has_node(u) else None
                    add_node(v, {"label": d.get("label", v), "type": "cross_ref"}, tgg)
                    add_edge_uniq(u, v, d.get("relation", "related_to"), True, tgg)
                    if tgg not in node_id_set:
                        node_id_set.add(tgg)
                        node_set[tgg] = {"id": tgg, "label": tgg,
                                         "type": "hive", "graph_id": tgg}

        # Keyword matching across all chain hives
        extra = q
        for gid in hive_chain:
            extra = extra.replace(gid, "").replace(gid.replace("-", " "), "")
        keywords = [w for w in extra.split() if len(w) > 3]

        for gid in chain_set:
            kg = self.graphs[gid]
            for node, data in kg.graph.nodes(data=True):
                label = data.get("label", "").lower()
                if any(kw in label or kw in node.lower() for kw in keywords):
                    add_node(node, data, gid)

        # Pull top concepts from each chain hive
        src_id, tgt_id = hive_chain[0], hive_chain[-1]
        for gid in hive_chain:
            kg = self.graphs[gid]
            concepts = [n for n, d in kg.graph.nodes(data=True)
                        if d.get("type") == "concept" and n not in node_id_set][:5]
            for n in concepts:
                add_node(n, kg.graph.nodes[n], gid)

        # Build explanation
        cross_edges = [e for e in edge_list if e.get("cross_graph")]
        path_edges = [e for e in edge_list if not e.get("cross_graph")]

        lines = []
        for ce in cross_edges[:4]:
            s_label = node_set.get(ce["source"], {}).get("label", ce["source"])
            t_label = node_set.get(ce["target"], {}).get("label", ce["target"])
            lines.append(f"**{s_label}** *{ce['relation']}* **{t_label}**")

        for pe in path_edges[:4]:
            s_label = node_set.get(pe["source"], {}).get("label", pe["source"])
            t_label = node_set.get(pe["target"], {}).get("label", pe["target"])
            lines.append(f"**{s_label}** → *{pe['relation']}* → **{t_label}**")

        chain_display = " → ".join(f"**{h}**" for h in hive_chain)
        explanation = f"### {chain_display}\n"
        if lines:
            explanation += "\n".join(lines[:6])
        else:
            explanation += f"No connections found between _{src_id}_ and _{tgt_id}_."

        return {
            "nodes": list(node_set.values()),
            "edges": edge_list,
            "explanation": explanation,
            "source": src_id,
            "target": tgt_id,
            "chain": hive_chain,
        }

    def _meta_path(self, src: str, tgt: str) -> list[str]:
        """Find shortest path through meta-graph from src to tgt."""
        if src not in self.graphs or tgt not in self.graphs:
            return [src, tgt]
        import collections
        adj: dict[str, list[str]] = {}
        for u, v, _ in self.meta_graph.edges(data=True):
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, []).append(u)
        q = collections.deque([(src, [src])])
        visited = {src}
        while q:
            cur, path = q.popleft()
            if cur == tgt:
                return path
            for nb in adj.get(cur, []):
                if nb not in visited:
                    visited.add(nb)
                    q.append((nb, path + [nb]))
        return [src, tgt]

    def _find_path_in_graphs(self, src: str, tgt: str,
                              src_gid: str, tgt_gid: str) -> list | None:
        """BFS for a path from src to tgt, searching source graph then target graph."""
        import collections
        src_kg = self.graphs.get(src_gid)
        tgt_kg = self.graphs.get(tgt_gid)
        if not src_kg or not tgt_kg:
            return None

        # BFS in source + target graphs combined (via cross edges)
        # Build adjacency list
        adj: dict[str, list[tuple[str, str, str]]] = {}
        def add_adj(u: str, v: str, rel: str, gid: str) -> None:
            if u not in adj:
                adj[u] = []
            adj[u].append((v, rel, gid))

        for gid, kg in [(src_gid, src_kg), (tgt_gid, tgt_kg)]:
            for u, v, d in kg.graph.edges(data=True):
                add_adj(u, v, d.get("relation", "related_to"), gid)
                add_adj(v, u, d.get("relation", "related_to"), gid)
            # cross edges from source to target
            if gid == src_gid:
                for u, v, d in kg.graph.edges(data=True):
                    if d.get("cross_graph") and d.get("target_graph") == tgt_gid:
                        add_adj(u, v, d.get("relation", "related_to"), src_gid)
                        add_adj(v, u, d.get("relation", "related_to"), tgt_gid)

        q: collections.deque = collections.deque([(src, [(src, src, "start", src_gid)])])
        visited: set[str] = set([src])
        while q:
            cur, path = q.popleft()
            if cur == tgt:
                return path[1:]  # skip the start sentinel
            for neighbor, rel, gid in adj.get(cur, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    q.append((neighbor, path + [(cur, neighbor, rel, gid)]))
        return None

    def stats(self) -> dict[str, Any]:
        total = {"graphs": len(self.graphs), "papers": 0, "concepts": 0,
                 "graph_refs": 0, "relations": 0, "cross_edges": 0}
        for kg in self.graphs.values():
            s = kg.stats()
            total["papers"] += s["papers"]
            total["concepts"] += s["concepts"]
            total["graph_refs"] += s["graph_refs"]
            total["relations"] += s["relations"]
            total["cross_edges"] += s["cross_edges"]
        total["meta_edges"] = self.meta_graph.number_of_edges()
        return total

    # ------------------------------------------------------------------
    # Meta-graph persistence
    # ------------------------------------------------------------------

    def _sync_meta_node(self, kg: KnowledgeGraph,
                        owner: str = "") -> None:
        gid = kg.graph_id
        if not self.meta_graph.has_node(gid):
            self.meta_graph.add_node(
                gid,
                label=gid,
                path=kg.path,
                type="knowledge_graph",
                visible=True,
                owner=owner,
            )
        else:
            if "visible" not in self.meta_graph.nodes[gid]:
                self.meta_graph.nodes[gid]["visible"] = True
            if owner and not self.meta_graph.nodes[gid].get("owner"):
                self.meta_graph.nodes[gid]["owner"] = owner
        # Restore cross-graph refs from the KG into meta-graph
        for ref in kg.get_all_graph_refs():
            tgt = ref["target_graph_id"]
            if tgt and tgt in self.graphs:
                if not self.meta_graph.has_edge(gid, tgt):
                    self.meta_graph.add_edge(gid, tgt,
                                             relation="references",
                                             label=ref["label"])
        self._save_meta()

    def _load_meta(self) -> None:
        if os.path.exists(self.meta_graph_path):
            with open(self.meta_graph_path) as f:
                data = json.load(f)
            self.meta_graph = nx.node_link_graph(data, multigraph=True, directed=True, edges="links")
            for _, d in self.meta_graph.nodes(data=True):
                d.setdefault("visible", True)

    def _save_meta(self) -> None:
        os.makedirs(os.path.dirname(self.meta_graph_path), exist_ok=True)
        data = nx.node_link_data(self.meta_graph, edges="links")
        with open(self.meta_graph_path, "w") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    @property
    def _collections_path(self) -> str:
        return os.path.join(os.path.dirname(self.meta_graph_path), "collections.json")

    def _load_collections(self) -> None:
        path = self._collections_path
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self.collections = data.get("collections", {})

    def _save_collections(self) -> None:
        path = self._collections_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"collections": self.collections}, f, indent=2)

    def create_collection(self, name: str, description: str = "") -> dict[str, Any]:
        cid = name.lower().replace(" ", "-")
        if cid in self.collections:
            raise ValueError(f"Collection '{cid}' already exists")
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
        collection = {
            "id": cid,
            "name": name,
            "description": description,
            "hive_ids": [],
            "created_at": ts,
            "updated_at": ts,
        }
        self.collections[cid] = collection
        self._save_collections()
        return dict(collection)

    def list_collections(self) -> list[dict[str, Any]]:
        result = []
        for cid, c in self.collections.items():
            result.append({
                "id": cid,
                "name": c.get("name", cid),
                "description": c.get("description", ""),
                "hive_count": len(c.get("hive_ids", [])),
                "created_at": c.get("created_at", ""),
                "updated_at": c.get("updated_at", ""),
            })
        result.sort(key=lambda x: x["name"].lower())
        return result

    def get_collection(self, cid: str) -> dict[str, Any]:
        c = self.collections.get(cid)
        if not c:
            raise ValueError(f"Collection '{cid}' not found")
        hives = []
        for hid in c.get("hive_ids", []):
            kg = self.graphs.get(hid)
            if kg:
                s = kg.stats()
                hives.append({
                    "id": hid,
                    "papers": s["papers"],
                    "concepts": s["concepts"],
                    "relations": s["relations"],
                })
        return {
            "id": c["id"],
            "name": c.get("name", cid),
            "description": c.get("description", ""),
            "hives": hives,
            "created_at": c.get("created_at", ""),
            "updated_at": c.get("updated_at", ""),
        }

    def delete_collection(self, cid: str) -> None:
        if cid not in self.collections:
            raise ValueError(f"Collection '{cid}' not found")
        del self.collections[cid]
        self._save_collections()

    def add_hive_to_collection(self, cid: str, hive_id: str) -> dict[str, Any]:
        c = self.collections.get(cid)
        if not c:
            raise ValueError(f"Collection '{cid}' not found")
        if hive_id not in self.graphs:
            raise ValueError(f"Hive '{hive_id}' not found")
        if hive_id not in c["hive_ids"]:
            c["hive_ids"].append(hive_id)
            c["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            self._save_collections()
        return self.get_collection(cid)

    def remove_hive_from_collection(self, cid: str, hive_id: str) -> dict[str, Any]:
        c = self.collections.get(cid)
        if not c:
            raise ValueError(f"Collection '{cid}' not found")
        if hive_id in c["hive_ids"]:
            c["hive_ids"].remove(hive_id)
            c["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
            self._save_collections()
        return self.get_collection(cid)

    def meta_graph_data(self, include_hidden: bool = False) -> dict[str, Any]:
        visible_nodes = set()
        for n, d in self.meta_graph.nodes(data=True):
            if include_hidden or d.get("visible", True):
                visible_nodes.add(n)
        nodes = []
        edges = []
        for n, d in self.meta_graph.nodes(data=True):
            if n not in visible_nodes:
                continue
            s = self.graphs[n].stats() if n in self.graphs else {}
        nodes.append({
            "id": n,
            "label": d.get("label", n),
            "type": "knowledge_graph",
            "visible": d.get("visible", True),
            "papers": s.get("papers", 0),
            "concepts": s.get("concepts", 0),
            "relations": s.get("relations", 0),
            "owner": d.get("owner", ""),
        })
        for u, v, d in self.meta_graph.edges(data=True):
            if u in visible_nodes and v in visible_nodes:
                edges.append({
                    "source": u,
                    "target": v,
                    "relation": d.get("relation", "references"),
                })
        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------
    # Hive comparison
    # ------------------------------------------------------------------

    def compare_hives(self, hive_ids: list[str]) -> dict[str, Any]:
        for hid in hive_ids:
            if hid not in self.graphs:
                raise ValueError(f"Hive '{hid}' not found")

        # Build query text from hive names for relation chaining
        display_names = [hid.replace("-", " ").lower() for hid in hive_ids]
        query_text = " and ".join(display_names) + " how are these related"
        relation_result = self.query_relation(query_text)

        # Find overlapping concepts by matching normalized labels
        concept_map: dict[str, list[dict[str, Any]]] = {}
        for hid in hive_ids:
            kg = self.graphs[hid]
            for node, data in kg.graph.nodes(data=True):
                if data.get("type") == "concept":
                    label = data.get("label", node).lower().strip()
                    concept_map.setdefault(label, []).append({
                        "hive_id": hid,
                        "node_id": node,
                        "label": data.get("label", node),
                        "definition": (data.get("definition", "") or "")[:200],
                    })

        overlaps = sorted(
            [{"concept": label, "occurrences": entries}
             for label, entries in concept_map.items() if len(entries) >= 2],
            key=lambda x: -len(x["occurrences"]),
        )

        # Build merge mapping: per-hive uid of shared concept -> single merged id
        merge_map: dict[str, str] = {}
        merged_node_data: dict[str, dict[str, Any]] = {}
        for o in overlaps:
            label = o["concept"]
            merged_id = f"_shared:{label}"
            occurrences = o["occurrences"]
            merged_node_data[merged_id] = {
                "id": merged_id,
                "label": occurrences[0]["label"],
                "type": "concept",
                "graphId": "shared",
                "hiveIds": [e["hive_id"] for e in occurrences],
                "shared": True,
            }
            for entry in occurrences:
                merge_map[f"{entry['hive_id']}:{entry['node_id']}"] = merged_id

        # Collect combined graph data with merged shared nodes
        combined_nodes: list[dict[str, Any]] = []
        combined_edges: list[dict[str, Any]] = []
        added_merged: set[str] = set()
        all_node_ids: set[str] = set()

        for hid in hive_ids:
            kg = self.graphs[hid]
            for n, d in kg.graph.nodes(data=True):
                uid = f"{hid}:{n}"
                if uid in merge_map:
                    merged_id = merge_map[uid]
                    if merged_id not in added_merged:
                        added_merged.add(merged_id)
                        combined_nodes.append(merged_node_data[merged_id])
                        all_node_ids.add(merged_id)
                else:
                    combined_nodes.append({
                        "id": uid,
                        "label": d.get("label", n)[:60],
                        "type": d.get("type", "unknown"),
                        "graphId": hid,
                        "originalId": n,
                        "shared": False,
                    })
                    all_node_ids.add(uid)

        seen_edges: set[tuple[str, str]] = set()
        for hid in hive_ids:
            kg = self.graphs[hid]
            for u, v, d in kg.graph.edges(data=True):
                suid = f"{hid}:{u}"
                tuid = f"{d.get('target_graph', hid)}:{v}"
                src = merge_map.get(suid, suid)
                tgt = merge_map.get(tuid, tuid)
                key = (src, tgt)
                if key not in seen_edges and src in all_node_ids and tgt in all_node_ids:
                    seen_edges.add(key)
                    combined_edges.append({
                        "source": src,
                        "target": tgt,
                        "relation": d.get("relation", "related_to"),
                        "cross_graph": d.get("cross_graph", False),
                    })

        # Build overlap-only sub-graph from merged nodes
        overlap_nodes = [n for n in combined_nodes if n["shared"]]
        overlap_node_ids = {n["id"] for n in overlap_nodes}
        overlap_edges = [e for e in combined_edges
                         if e["source"] in overlap_node_ids and e["target"] in overlap_node_ids]

        # Build explanation
        chain_display = " → ".join(f"**{h}**" for h in relation_result.get("chain", hive_ids))
        explanation = f"### {chain_display}\n"
        if overlaps:
            explanation += f"\n**Overlapping concepts:** {len(overlaps)} found\n"
            for o in overlaps[:10]:
                hives_str = ", ".join(e["hive_id"] for e in o["occurrences"])
                explanation += f"- _{o['concept']}_ (in {hives_str})\n"
        if relation_result.get("explanation"):
            explanation += "\n" + relation_result["explanation"]

        return {
            "hives": list(hive_ids),
            "chain": relation_result.get("chain", hive_ids),
            "overlaps": overlaps[:30],
            "overlap_count": len(overlaps),
            "nodes": combined_nodes,
            "edges": combined_edges,
            "overlap_nodes": overlap_nodes,
            "overlap_edges": overlap_edges,
            "explanation": explanation,
        }

    # ------------------------------------------------------------------
    # Hive sharing (export/import)
    # ------------------------------------------------------------------

    def export_hive_data(self, hive_id: str) -> dict[str, Any]:
        """Export a hive's graph data as a portable JSON blob for sharing."""
        kg = self.graphs.get(hive_id)
        if not kg:
            raise ValueError(f"Hive '{hive_id}' not found")
        graph_data = nx.node_link_data(kg.graph, edges="links")
        return {
            "hivemind_export": True,
            "version": 1,
            "source_hive": hive_id,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "graph": graph_data,
        }

    def import_hive_data(self, data: dict[str, Any],
                         target_name: str | None = None,
                         merge_similar: bool = True) -> dict[str, Any]:
        """Import a hive from exported data, with optional similarity merging."""
        if not data.get("hivemind_export"):
            raise ValueError("Invalid export format: missing hivemind_export marker")
        source_hive = data.get("source_hive", "unknown")

        # Determine the local hive name
        local_name = target_name or source_hive
        if local_name in self.graphs:
            base, idx = local_name, 1
            while f"{base}_{idx}" in self.graphs:
                idx += 1
            local_name = f"{base}_{idx}"

        # Reconstruct the KnowledgeGraph from the exported node-link data
        graph_data = data.get("graph", {})
        kg = KnowledgeGraph.__new__(KnowledgeGraph)
        kg.graph_id = local_name
        kg.graph = nx.node_link_graph(graph_data, multigraph=True, directed=True, edges="links")
        kg.path = ""
        kg.max_backups = self.max_backups

        # Update graph_id on all nodes to the new local name
        for _, d in kg.graph.nodes(data=True):
            d["graph_id"] = local_name
        # Relabel cross-graph edge target_graph references from source hive to local
        for _, _, d in kg.graph.edges(data=True):
            if d.get("target_graph") == source_hive:
                d["target_graph"] = local_name

        # Set storage path and save
        meta_dir = os.path.dirname(self.meta_graph_path)
        hives_dir = os.path.join(os.path.dirname(meta_dir), "hives")
        safe_name = local_name.replace(" ", "_").replace("/", "_")
        storage_path = os.path.join(hives_dir, safe_name, "data", "graph", "knowledge_graph.json")
        kg.path = storage_path
        kg.save()

        self.register_graph(kg)

        report: dict[str, Any] = {
            "hive_id": local_name,
            "source_hive": source_hive,
            "nodes": kg.graph.number_of_nodes(),
            "edges": kg.graph.number_of_edges(),
            "merged": [],
            "new_concepts": [],
        }

        # Similarity merge: find matching concepts across existing hives
        if merge_similar:
            concepts: list[tuple[str, str, str]] = []  # (node_id, label, definition)
            for n, d in kg.graph.nodes(data=True):
                if d.get("type") == "concept":
                    concepts.append((n, d.get("label", ""), d.get("definition", "")))

            # Search each existing hive for similar concepts
            for nid, label, defn in concepts:
                if not label:
                    continue
                best_match: tuple[str, str, str] | None = None  # (hive_id, matched_label, matched_node_id)
                best_score = 0.0
                words = set(label.lower().split())
                for gid, other_kg in self.graphs.items():
                    if gid == local_name:
                        continue
                    found = other_kg.find_similar_concept(label, threshold=0.0)
                    # find_similar_concept returns the label of the best match; we need the node_id too
                    # Let's do the search inline instead
                    for on, od in other_kg.graph.nodes(data=True):
                        if od.get("type") != "concept":
                            continue
                        other_label = od.get("label", "")
                        other_words = set(other_label.lower().split())
                        if not words or not other_words:
                            continue
                        score = len(words & other_words) / len(words | other_words)
                        if score > best_score:
                            best_score = score
                            best_match = (gid, other_label, on)

                if best_match and best_score >= 0.5:
                    gid, matched_label, matched_node_id = best_match
                    kg.add_cross_edge(nid, gid, matched_node_id, "related_to")
                    kg.save()
                    report["merged"].append({
                        "imported_concept": label,
                        "matched_concept": matched_label,
                        "matched_hive": gid,
                        "similarity": round(best_score, 3),
                    })
                else:
                    report["new_concepts"].append(label)

        return report

    # ------------------------------------------------------------------
    # Peer-to-peer sharing
    # ------------------------------------------------------------------

    @property
    def _peers_path(self) -> str:
        return os.path.join(os.path.dirname(self.meta_graph_path), "peers.json")

    def _load_peers(self) -> None:
        path = self._peers_path
        self._peers: dict[str, dict[str, Any]] = {}
        self._instance_id: str = ""
        self._instance_name: str = ""
        self._public_url: str = ""
        self._instance_secret: str = ""
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            self._peers = data.get("peers", {})
            self._instance_id = data.get("instance_id", "")
            self._instance_name = data.get("instance_name", "")
            self._public_url = data.get("public_url", "")
            self._instance_secret = data.get("instance_secret", "")
        if not self._instance_id:
            self._instance_id = str(uuid.uuid4())
        if not self._instance_secret:
            self._instance_secret = hashlib.sha256(os.urandom(64)).hexdigest()
            self._save_peers()

    def _save_peers(self) -> None:
        path = self._peers_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({
                "instance_id": self._instance_id,
                "instance_name": self._instance_name,
                "public_url": self._public_url,
                "instance_secret": self._instance_secret,
                "peers": self._peers,
            }, f, indent=2)

    def _fingerprint(self) -> str:
        h = hashlib.sha256(self._instance_secret.encode()).hexdigest()
        return ":".join(h[i:i+4] for i in range(0, 20, 4))

    def set_public_url(self, url: str) -> None:
        self._public_url = url.rstrip("/")
        self._save_peers()

    def set_instance_name(self, name: str) -> None:
        self._instance_name = name.strip()
        self._save_peers()

    def instance_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            "instance_id": self._instance_id,
            "instance_name": self._instance_name,
            "fingerprint": self._fingerprint(),
            "name": self._instance_name or (self._public_url.split("//")[-1] if self._public_url else "local"),
            "version": 1,
            "hive_count": len(self.graphs),
            "hives": [{"id": h["id"], "papers": h["papers"],
                       "concepts": h["concepts"], "relations": h["relations"]}
                      for h in self.list_graphs()],
            "peer_count": len(self._peers),
            "tls": self._public_url.startswith("https") if self._public_url else False,
        }
        if self._public_url:
            info["url"] = self._public_url
        return info

    def create_invite(self, ttl: int = 600) -> dict[str, Any]:
        """Generate a signed one-time pairing token."""
        token = str(uuid.uuid4())
        expiry = int(time.time()) + ttl
        payload = f"{token}:{expiry}"
        sig = hmac.new(self._instance_secret.encode(), payload.encode(),
                       hashlib.sha256).hexdigest()[:12]
        invite_token = f"{token}:{expiry}:{sig}"
        return {
            "token": invite_token,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expiry)),
            "url": self._public_url or "",
        }

    def verify_invite(self, invite_token: str) -> bool:
        """Verify a signed pairing token."""
        try:
            parts = invite_token.split(":")
            if len(parts) < 3:
                return False
            token, expiry_str, sig = parts[0], parts[1], ":".join(parts[2:])
            expiry = int(expiry_str)
            if int(time.time()) > expiry:
                return False
            payload = f"{token}:{expiry}"
            expected = hmac.new(self._instance_secret.encode(), payload.encode(),
                                hashlib.sha256).hexdigest()[:12]
            if not hmac.compare_digest(expected, sig):
                return False
            # Mark token as used (store in a set)
            if not hasattr(self, "_used_tokens"):
                self._used_tokens = set()
            if token in self._used_tokens:
                return False
            self._used_tokens.add(token)
            return True
        except (ValueError, IndexError):
            return False

    def add_peer(self, url: str, name: str = "",
                 peer_fingerprint: str = "") -> dict[str, Any]:
        url = url.rstrip("/")
        if url == self._public_url:
            raise ValueError("Cannot add self as a peer")
        pid = str(uuid.uuid4())[:8]
        entry: dict[str, Any] = {
            "id": pid,
            "name": name or url,
            "url": url,
            "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if peer_fingerprint:
            entry["fingerprint"] = peer_fingerprint
        self._peers[pid] = entry
        self._save_peers()
        return dict(self._peers[pid])

    def find_peer_by_url(self, url: str) -> dict[str, Any] | None:
        url = url.rstrip("/")
        for p in self._peers.values():
            if p["url"] == url:
                return p
        return None

    def pair_with_peer(self, url: str, token: str | None = None) -> dict[str, Any]:
        """Bidirectional pairing: fetch remote info, register as peer,
        then register self on the remote."""
        url = url.rstrip("/")
        info_url = urljoin(url, "/api/peering/info")
        pair_url = urljoin(url, "/api/peering/pair")

        # Fetch remote instance info and fingerprint
        try:
            req = Request(info_url, headers={"User-Agent": "HiveMind/1.0"})
            with urlopen(req, timeout=15) as resp:
                remote_info = json.loads(resp.read().decode())
        except Exception as e:
            raise ValueError(f"Failed to reach peer at {url}: {e}")

        remote_id = remote_info.get("instance_id", "")
        if remote_id == self._instance_id:
            raise ValueError("Cannot pair with self")

        remote_name = remote_info.get("name", url)
        remote_fingerprint = remote_info.get("fingerprint", "")
        remote_tls = remote_info.get("tls", False)

        if not remote_tls and not token:
            raise ValueError(
                "Remote instance is not using TLS. "
                "Use a pairing token for secure pairing: "
                "run 'hivemind peers invite' on the remote and provide the token."
            )

        # Check if already paired
        existing = self.find_peer_by_url(url)
        if existing:
            return {"status": "already_paired", "peer": existing}

        # Register the remote as a local peer
        peer = self.add_peer(url, remote_name, remote_fingerprint)

        # Register self on the remote (bidirectional), passing token if we have one
        self_name = self._public_url.split("//")[-1] if self._public_url else "local"
        pair_body: dict[str, Any] = {
            "peer_url": self._public_url or "",
            "peer_name": self_name,
            "instance_id": self._instance_id,
            "fingerprint": self._fingerprint(),
        }
        if token:
            pair_body["token"] = token

        pair_payload = json.dumps(pair_body).encode()
        try:
            pair_req = Request(pair_url, data=pair_payload,
                               headers={
                                   "User-Agent": "HiveMind/1.0",
                                   "Content-Type": "application/json",
                               })
            with urlopen(pair_req, timeout=15) as resp:
                pair_result = json.loads(resp.read().decode())
            remote_added = pair_result.get("status") == "ok"
            remote_error = pair_result.get("error", "")
        except Exception as e:
            remote_added = False
            remote_error = str(e)

        return {
            "status": "paired",
            "peer": peer,
            "remote": {
                "instance_id": remote_id,
                "name": remote_name,
                "url": url,
                "hives": remote_info.get("hive_count", 0),
                "fingerprint": remote_fingerprint,
                "tls": remote_tls,
            },
            "remote_registered": remote_added,
            "remote_error": remote_error if not remote_added else "",
        }

    def list_peers(self) -> list[dict[str, Any]]:
        return sorted(self._peers.values(), key=lambda p: p["name"].lower())

    def remove_peer(self, pid: str) -> None:
        if pid not in self._peers:
            raise ValueError(f"Peer '{pid}' not found")
        del self._peers[pid]
        self._save_peers()

    def pull_peer_hives(self, peer_id: str,
                        hive_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch all hives (or a specific one) from a peer and import locally."""
        peer = self._peers.get(peer_id)
        if not peer:
            raise ValueError(f"Peer '{peer_id}' not found")
        base = peer["url"]

        reports: list[dict[str, Any]] = []

        if hive_id:
            remote_hives = [{"id": hive_id}]
        else:
            try:
                req = Request(urljoin(base, "/api/peering/hives"),
                              headers={"User-Agent": "HiveMind/1.0"})
                with urlopen(req, timeout=30) as resp:
                    remote_hives = json.loads(resp.read().decode())
            except Exception as e:
                raise ValueError(f"Failed to fetch hive list from {base}: {e}")

        for rh in remote_hives:
            hid = rh["id"]
            try:
                req = Request(urljoin(base, f"/api/peering/hive/{hid}"),
                              headers={"User-Agent": "HiveMind/1.0"})
                with urlopen(req, timeout=60) as resp:
                    export_data = json.loads(resp.read().decode())
            except Exception as e:
                reports.append({"hive_id": hid, "status": "error",
                                "error": str(e)})
                continue

            try:
                report = self.import_hive_data(export_data,
                                               target_name=None,
                                               merge_similar=True)
                report["status"] = "ok"
                reports.append(report)
            except ValueError as e:
                reports.append({"hive_id": hid, "status": "error",
                                "error": str(e)})

        return reports

    def set_hive_visibility(self, gid: str, visible: bool) -> None:
        if self.meta_graph.has_node(gid):
            self.meta_graph.nodes[gid]["visible"] = visible
            self._save_meta()
        elif gid in self.graphs:
            self.meta_graph.add_node(gid, label=gid, type="knowledge_graph",
                                     visible=visible)
            self._save_meta()
