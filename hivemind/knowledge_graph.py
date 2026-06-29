import json
import logging
import os
import shutil
import time
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)

VALID_RELATIONS = {
    "cites", "introduces", "uses", "improves", "extends",
    "compares", "contrasts", "proposes", "related_to",
    "nests", "references",
}


class KnowledgeGraph:
    def __init__(self, storage_path: str, graph_id: str = "",
                 max_backups: int = 20):
        self.path = storage_path
        self.graph_id = graph_id
        self.max_backups = max_backups
        os.makedirs(os.path.dirname(storage_path), exist_ok=True)
        self.graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self.load()

    def add_paper(self, data: dict) -> str:
        node_id = f"paper:{data['arxiv_id']}"
        self.graph.add_node(
            node_id,
            type="paper",
            label=data["title"],
            arxiv_id=data["arxiv_id"],
            authors=", ".join(data["authors"]),
            published=data.get("published", ""),
            abstract=data.get("abstract", ""),
            categories=data.get("categories", []),
            graph_id=self.graph_id,
        )
        return node_id

    def add_concept(self, name: str, definition: str = "",
                    concept_type: str = "concept") -> str:
        name = " ".join(name.split())
        node_id = f"concept:{name}"
        if not self.graph.has_node(node_id):
            self.graph.add_node(
                node_id,
                type="concept",
                label=name,
                definition=definition,
                concept_type=concept_type,
                graph_id=self.graph_id,
            )
        else:
            existing = self.graph.nodes[node_id]
            if not existing.get("definition") and definition:
                existing["definition"] = definition
        return node_id

    def add_graph_ref(self, target_graph_id: str, label: str = "",
                      relation: str = "references") -> str:
        node_id = f"graph_ref:{target_graph_id}"
        if not self.graph.has_node(node_id):
            self.graph.add_node(
                node_id,
                type="graph_ref",
                label=label or target_graph_id,
                target_graph_id=target_graph_id,
                graph_id=self.graph_id,
            )
            if self.graph.has_node(target_graph_id):
                self.add_edge(node_id, target_graph_id, relation)
        return node_id

    def add_cross_edge(self, source_id: str, target_graph_id: str,
                       target_node_id: str, relation: str = "related_to") -> None:
        if relation not in VALID_RELATIONS:
            relation = "related_to"
        cross_target = f"{target_graph_id}:{target_node_id}"
        self.graph.add_edge(source_id, cross_target, relation=relation,
                            cross_graph=True, target_graph=target_graph_id)

    def has_paper(self, arxiv_id: str) -> bool:
        return self.graph.has_node(f"paper:{arxiv_id}")

    def has_any_paper_id(self, arxiv_ids: list[str]) -> set[str]:
        return {aid for aid in arxiv_ids if self.has_paper(aid)}

    def add_edge(self, source_id: str, target_id: str,
                 relation: str = "related_to") -> None:
        if relation not in VALID_RELATIONS:
            relation = "related_to"
        self.graph.add_edge(source_id, target_id, relation=relation)

    def merge_concepts(self, source_name: str, target_name: str) -> None:
        src = f"concept:{source_name}"
        tgt = f"concept:{target_name}"
        if not (self.graph.has_node(src) and self.graph.has_node(tgt)):
            return
        # Move incoming edges
        for pred, _, d in list(self.graph.in_edges(src, data=True)):
            self.graph.add_edge(
                pred, tgt, relation=d.get("relation", "related_to")
            )
        # Move outgoing edges
        for _, succ, d in list(self.graph.out_edges(src, data=True)):
            self.graph.add_edge(
                tgt, succ, relation=d.get("relation", "related_to")
            )
        self.graph.remove_node(src)

    def find_similar_concept(self, name: str,
                             threshold: float = 0.85) -> str | None:
        words = set(name.lower().split())
        best_match: str | None = None
        best_score = 0.0
        for node, data in self.graph.nodes(data=True):
            if data.get("type") != "concept":
                continue
            other = set(data.get("label", "").lower().split())
            if not words or not other:
                continue
            score = len(words & other) / len(words | other)
            if score > best_score:
                best_score = score
                best_match = data["label"]
        return best_match if best_score >= threshold else None

    def get_papers_for_concept(self, concept_name: str) -> list[str]:
        node_id = f"concept:{concept_name}"
        papers: set[str] = set()
        if not self.graph.has_node(node_id):
            return []
        for n in self.graph.predecessors(node_id):
            if self.graph.nodes[n].get("type") == "paper":
                papers.add(n)
        for n in self.graph.successors(node_id):
            if self.graph.nodes[n].get("type") == "paper":
                papers.add(n)
        return list(papers)

    def get_all_concepts(self) -> list[dict[str, Any]]:
        return [
            {
                "id": n,
                "name": d.get("label", ""),
                "definition": d.get("definition", ""),
                "type": d.get("concept_type", "concept"),
            }
            for n, d in self.graph.nodes(data=True)
            if d.get("type") == "concept"
        ]

    def get_all_papers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": n,
                "title": d.get("label", ""),
                "arxiv_id": d.get("arxiv_id", ""),
            }
            for n, d in self.graph.nodes(data=True)
            if d.get("type") == "paper"
        ]

    def get_all_graph_refs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": n,
                "label": d.get("label", ""),
                "target_graph_id": d.get("target_graph_id", ""),
            }
            for n, d in self.graph.nodes(data=True)
            if d.get("type") == "graph_ref"
        ]

    def get_cross_edges(self) -> list[dict[str, Any]]:
        return [
            {
                "source": u, "target": v,
                "relation": d.get("relation", "related_to"),
                "target_graph": d.get("target_graph", ""),
            }
            for u, v, d in self.graph.edges(data=True)
            if d.get("cross_graph")
        ]

    def get_related_concepts(self, concept_name: str) -> list[str]:
        node_id = f"concept:{concept_name}"
        related: set[str] = set()
        if not self.graph.has_node(node_id):
            return []
        for n in self.graph.predecessors(node_id):
            if self.graph.nodes[n].get("type") == "concept":
                related.add(self.graph.nodes[n].get("label", ""))
        for n in self.graph.successors(node_id):
            if self.graph.nodes[n].get("type") == "concept":
                related.add(self.graph.nodes[n].get("label", ""))
        return list(related)

    # ------------------------------------------------------------------
    # Persistence with backups
    # ------------------------------------------------------------------

    def _backup_dir(self) -> str:
        bdir = os.path.join(os.path.dirname(self.path), "backups")
        os.makedirs(bdir, exist_ok=True)
        return bdir

    def save(self) -> None:
        data = nx.node_link_data(self.graph, edges="links")
        data["graph_id"] = self.graph_id
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Backup current file if it exists
        if os.path.exists(self.path):
            ts = time.strftime("%Y%m%d_%H%M%S")
            backup = os.path.join(self._backup_dir(), f"{ts}.json")
            shutil.copy2(self.path, backup)
            self._prune_backups()
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def _prune_backups(self) -> None:
        bdir = self._backup_dir()
        backups = sorted(
            [f for f in os.listdir(bdir) if f.endswith(".json")],
            reverse=True,
        )
        for old in backups[self.max_backups:]:
            os.remove(os.path.join(bdir, old))
            logger.debug("Pruned old backup: %s", old)

    def load(self) -> None:
        if os.path.exists(self.path):
            with open(self.path) as f:
                data = json.load(f)
            self.graph = nx.node_link_graph(data, multigraph=True, directed=True, edges="links")
            self.graph_id = data.get("graph_id", self.graph_id)

    def list_backups(self) -> list[dict[str, Any]]:
        bdir = self._backup_dir()
        backups = []
        for fn in sorted(os.listdir(bdir), reverse=True):
            if fn.endswith(".json"):
                fpath = os.path.join(bdir, fn)
                size = os.path.getsize(fpath)
                ts = fn.replace(".json", "")
                try:
                    with open(fpath) as f:
                        data = json.load(f)
                    papers = sum(1 for n in data.get("nodes", []) if n.get("type") == "paper")
                    concepts = sum(1 for n in data.get("nodes", []) if n.get("type") == "concept")
                except Exception:
                    papers = concepts = 0
                backups.append({
                    "version": ts,
                    "timestamp": ts,
                    "size": size,
                    "papers": papers,
                    "concepts": concepts,
                })
        return backups

    def get_backup_data(self, version: str) -> dict | None:
        fpath = os.path.join(self._backup_dir(), f"{version}.json")
        if os.path.exists(fpath):
            with open(fpath) as f:
                return json.load(f)
        return None

    def restore(self, version: str) -> str:
        data = self.get_backup_data(version)
        if not data:
            raise ValueError(f"Backup '{version}' not found")
        # Backup current before restoring
        self.save()
        self.graph = nx.node_link_graph(data, multigraph=True, directed=True, edges="links")
        self.graph_id = data.get("graph_id", self.graph_id)
        self.save()
        return f"Restored hive '{self.graph_id}' to version {version}"

    def stats(self) -> dict[str, int]:
        papers = sum(
            1 for _, d in self.graph.nodes(data=True) if d.get("type") == "paper"
        )
        concepts = sum(
            1 for _, d in self.graph.nodes(data=True) if d.get("type") == "concept"
        )
        graph_refs = sum(
            1 for _, d in self.graph.nodes(data=True) if d.get("type") == "graph_ref"
        )
        cross_edges = sum(
            1 for _, _, d in self.graph.edges(data=True) if d.get("cross_graph")
        )
        return {
            "papers": papers,
            "concepts": concepts,
            "graph_refs": graph_refs,
            "relations": self.graph.number_of_edges(),
            "cross_edges": cross_edges,
        }
