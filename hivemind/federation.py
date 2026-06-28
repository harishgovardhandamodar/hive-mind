import json
import os
from typing import Any

import networkx as nx

from .knowledge_graph import KnowledgeGraph


class Federation:
    """Manages multiple KnowledgeGraphs, providing cross-graph linking
    and unified queries across all graphs in the federation."""

    def __init__(self, meta_graph_path: str):
        self.meta_graph_path = meta_graph_path
        self.graphs: dict[str, KnowledgeGraph] = {}
        self.meta_graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._load_meta()

    # ------------------------------------------------------------------
    # Graph lifecycle
    # ------------------------------------------------------------------

    def register_graph(self, graph: KnowledgeGraph) -> None:
        gid = graph.graph_id or os.path.splitext(os.path.basename(graph.path))[0]
        graph.graph_id = gid
        self.graphs[gid] = graph
        self._sync_meta_node(graph)

    def create_graph(self, graph_id: str, storage_path: str) -> KnowledgeGraph:
        kg = KnowledgeGraph(storage_path, graph_id=graph_id)
        self.register_graph(kg)
        return kg

    def load_graph(self, storage_path: str, graph_id: str = "") -> KnowledgeGraph:
        kg = KnowledgeGraph(storage_path, graph_id=graph_id)
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
            result.append({
                "id": gid,
                "path": kg.path,
                "papers": s["papers"],
                "concepts": s["concepts"],
                "graph_refs": s["graph_refs"],
                "relations": s["relations"],
                "cross_edges": s["cross_edges"],
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
        q = query.lower()
        results = []
        for gid, kg in self.graphs.items():
            for node, data in kg.graph.nodes(data=True):
                label = data.get("label", "")
                if q in label.lower() or q in node.lower():
                    results.append({
                        "graph_id": gid,
                        "node_id": node,
                        "label": label,
                        "type": data.get("type", "unknown"),
                        "definition": data.get("definition", ""),
                    })
        return results

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
            )
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

    def _save_meta(self) -> None:
        os.makedirs(os.path.dirname(self.meta_graph_path), exist_ok=True)
        data = nx.node_link_data(self.meta_graph, edges="links")
        with open(self.meta_graph_path, "w") as f:
            json.dump(data, f, indent=2)

    def meta_graph_data(self) -> dict[str, Any]:
        nodes = []
        edges = []
        for n, d in self.meta_graph.nodes(data=True):
            s = self.graphs[n].stats() if n in self.graphs else {}
            nodes.append({
                "id": n,
                "label": d.get("label", n),
                "type": "knowledge_graph",
                "papers": s.get("papers", 0),
                "concepts": s.get("concepts", 0),
                "relations": s.get("relations", 0),
            })
        for u, v, d in self.meta_graph.edges(data=True):
            edges.append({
                "source": u,
                "target": v,
                "relation": d.get("relation", "references"),
            })
        return {"nodes": nodes, "edges": edges}
