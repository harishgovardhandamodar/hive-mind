import json
import math
import os
import re
import time
from collections import Counter
from typing import Any

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
        self._load_meta()
        self._load_collections()

    # ------------------------------------------------------------------
    # Graph lifecycle
    # ------------------------------------------------------------------

    def register_graph(self, graph: KnowledgeGraph) -> None:
        gid = graph.graph_id or os.path.splitext(os.path.basename(graph.path))[0]
        graph.graph_id = gid
        self.graphs[gid] = graph
        self._sync_meta_node(graph)

    def create_graph(self, graph_id: str, storage_path: str) -> KnowledgeGraph:
        kg = KnowledgeGraph(storage_path, graph_id=graph_id, max_backups=self.max_backups)
        self.register_graph(kg)
        return kg

    def load_graph(self, storage_path: str, graph_id: str = "") -> KnowledgeGraph:
        kg = KnowledgeGraph(storage_path, graph_id=graph_id, max_backups=self.max_backups)
        self.register_graph(kg)
        return kg

    def remove_graph(self, graph_id: str) -> None:
        self.graphs.pop(graph_id, None)
        if self.meta_graph.has_node(graph_id):
            self.meta_graph.remove_node(graph_id)
        self._save_meta()

    def get_graph(self, graph_id: str) -> KnowledgeGraph | None:
        return self.graphs.get(graph_id)

    def list_graphs(self) -> list[dict[str, Any]]:
        result = []
        for gid, kg in self.graphs.items():
            s = kg.stats()
            visible = self.meta_graph.nodes[gid].get("visible", True) if self.meta_graph.has_node(gid) else True
            result.append({
                "id": gid,
                "path": kg.path,
                "papers": s["papers"],
                "concepts": s["concepts"],
                "graph_refs": s["graph_refs"],
                "relations": s["relations"],
                "cross_edges": s["cross_edges"],
                "visible": visible,
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

    def connect_concepts(self, source_graph: str, concept_a: str,
                         target_graph: str, concept_b: str,
                         relation: str = "related_to") -> None:
        source_node = f"concept:{concept_a}"
        target_node = f"concept:{concept_b}"
        self.add_cross_edge(source_graph, source_node,
                            target_graph, target_node, relation)

    # ------------------------------------------------------------------
    # Unified queries
    # ------------------------------------------------------------------

    def unified_search(self, query: str) -> list[dict[str, Any]]:
        q = query.lower().strip()
        if not q:
            return []

        # tokenize query
        q_tokens = self._tokenize(q)
        if not q_tokens:
            return []

        # collect all documents (node text fields)
        docs: list[tuple[str, str, str, str, str, str]] = []  # (gid, node_id, label, type, def, text)
        for gid, kg in self.graphs.items():
            for node, data in kg.graph.nodes(data=True):
                label = data.get("label", "")
                defn = data.get("definition", "")
                text = f"{label} {defn}".lower()
                docs.append((gid, node, label, data.get("type", "unknown"), defn, text))

        # TF–IDF scoring
        N = len(docs)
        df: dict[str, int] = Counter()
        doc_vectors: list[Counter] = []
        for _, _, _, _, _, text in docs:
            tokens = self._tokenize(text)
            doc_vectors.append(Counter(tokens))
            for t in set(tokens):
                df[t] += 1

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

    def _sync_meta_node(self, kg: KnowledgeGraph) -> None:
        gid = kg.graph_id
        if not self.meta_graph.has_node(gid):
            self.meta_graph.add_node(
                gid,
                label=gid,
                path=kg.path,
                type="knowledge_graph",
                visible=True,
            )
        else:
            if "visible" not in self.meta_graph.nodes[gid]:
                self.meta_graph.nodes[gid]["visible"] = True
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
            })
        for u, v, d in self.meta_graph.edges(data=True):
            if u in visible_nodes and v in visible_nodes:
                edges.append({
                    "source": u,
                    "target": v,
                    "relation": d.get("relation", "references"),
                })
        return {"nodes": nodes, "edges": edges}

    def set_hive_visibility(self, gid: str, visible: bool) -> None:
        if self.meta_graph.has_node(gid):
            self.meta_graph.nodes[gid]["visible"] = visible
            self._save_meta()
        elif gid in self.graphs:
            self.meta_graph.add_node(gid, label=gid, type="knowledge_graph",
                                     visible=visible)
            self._save_meta()
