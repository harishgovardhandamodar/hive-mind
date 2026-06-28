import json
import os
from typing import Any

import networkx as nx

from .config import load as load_config
from .federation import Federation
from .knowledge_graph import KnowledgeGraph


class HiveMind:
    """Top-level orchestrator that manages the federation of knowledge graphs
    and provides a unified interface for CLI and server."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.federation = Federation(self.config["meta_graph_path"])
        self._discover_hives()

    # ------------------------------------------------------------------
    # Discovery & loading
    # ------------------------------------------------------------------

    def _discover_hives(self) -> None:
        hives_dir = self.config["hives_dir"]
        if not os.path.isdir(hives_dir):
            return
        for entry in os.listdir(hives_dir):
            hive_path = os.path.join(hives_dir, entry)
            graph_file = os.path.join(hive_path, "data", "graph",
                                      "knowledge_graph.json")
            if os.path.isfile(graph_file):
                gid = entry
                if not self.federation.get_graph(gid):
                    kg = KnowledgeGraph(graph_file, graph_id=gid)
                    self.federation.register_graph(kg)

    def create_hive(self, name: str) -> str:
        hives_dir = self.config["hives_dir"]
        hive_path = os.path.join(hives_dir, name)
        graph_dir = os.path.join(hive_path, "data", "graph")
        os.makedirs(graph_dir, exist_ok=True)
        graph_file = os.path.join(graph_dir, "knowledge_graph.json")
        kg = self.federation.create_graph(name, graph_file)
        kg.save()
        return hive_path

    def add_graph_to_hive(self, hive_name: str, graph: KnowledgeGraph) -> None:
        self.federation.register_graph(graph)

    # ------------------------------------------------------------------
    # Federation operations
    # ------------------------------------------------------------------

    def link_hives(self, source: str, target: str,
                   relation: str = "references") -> None:
        self.federation.link_graphs(source, target, relation)

    def connect_concepts(self, source_graph: str, concept_a: str,
                         target_graph: str, concept_b: str,
                         relation: str = "related_to") -> None:
        self.federation.connect_concepts(source_graph, concept_a,
                                         target_graph, concept_b, relation)

    def import_from_arxiv_to_obsidian(self, source_path: str,
                                      hive_name: str | None = None) -> str:
        graph_file = os.path.join(source_path, "data", "graph",
                                  "knowledge_graph.json")
        if not os.path.isfile(graph_file):
            raise FileNotFoundError(
                f"No knowledge_graph.json found in {source_path}"
            )
        gid = hive_name or os.path.basename(os.path.normpath(source_path))
        kg = self.federation.load_graph(graph_file, graph_id=gid)
        kg.save()
        return gid

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def unified_search(self, query: str) -> list[dict[str, Any]]:
        return self.federation.unified_search(query)

    def list_hives(self) -> list[dict[str, Any]]:
        return self.federation.list_graphs()

    def get_hive_graph(self, hive_id: str) -> KnowledgeGraph | None:
        return self.federation.get_graph(hive_id)

    def get_all_nodes(self) -> list[dict[str, Any]]:
        return self.federation.get_all_nodes()

    def get_all_edges(self) -> list[dict[str, Any]]:
        return self.federation.get_all_edges()

    def meta_graph(self) -> dict[str, Any]:
        return self.federation.meta_graph_data()

    def query_relation(self, text: str) -> dict[str, Any]:
        return self.federation.query_relation(text)

    def stats(self) -> dict[str, Any]:
        return self.federation.stats()
