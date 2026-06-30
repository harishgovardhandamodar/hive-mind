import json
import os
from typing import Any

import networkx as nx

from .auth import AccessControl
from .config import load as load_config
from .embeddings import VectorStore
from .exporter import export_jsonld, export_obsidian
from .federation import Federation
from .knowledge_graph import KnowledgeGraph


class HiveMind:
    """Top-level orchestrator that manages the federation of knowledge graphs
    and provides a unified interface for CLI and server."""

    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.federation = Federation(
            self.config["meta_graph_path"],
            max_backups=self.config.get("max_backups", 20),
        )
        self.auth = AccessControl(self.config)
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
                    kg = KnowledgeGraph(
                        graph_file, graph_id=gid,
                        max_backups=self.config.get("max_backups", 20),
                    )
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

    def set_hive_visibility(self, hive_id: str, visible: bool) -> None:
        self.federation.set_hive_visibility(hive_id, visible)

    def query_relation(self, text: str) -> dict[str, Any]:
        return self.federation.query_relation(text)

    # ------------------------------------------------------------------
    # Backups & rollback
    # ------------------------------------------------------------------

    def list_backups(self, hive_id: str) -> list[dict[str, Any]]:
        kg = self.federation.get_graph(hive_id)
        if not kg:
            raise ValueError(f"Hive '{hive_id}' not found")
        return kg.list_backups()

    def get_backup(self, hive_id: str, version: str) -> dict | None:
        kg = self.federation.get_graph(hive_id)
        if not kg:
            raise ValueError(f"Hive '{hive_id}' not found")
        return kg.get_backup_data(version)

    def rollback(self, hive_id: str, version: str) -> str:
        kg = self.federation.get_graph(hive_id)
        if not kg:
            raise ValueError(f"Hive '{hive_id}' not found")
        return kg.restore(version)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_hive(self, hive_id: str, fmt: str = "jsonld",
                    output_dir: str | None = None) -> Any:
        kg = self.federation.get_graph(hive_id)
        if not kg:
            raise ValueError(f"Hive '{hive_id}' not found")
        if fmt == "jsonld":
            return export_jsonld(kg, graph_id=hive_id)
        elif fmt == "obsidian":
            return export_obsidian(kg, graph_id=hive_id, output_dir=output_dir)
        raise ValueError(f"Unknown export format: {fmt}")

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    def auth_create_key(self, name: str) -> dict[str, Any]:
        return self.auth.create_key(name)

    def auth_list_keys(self) -> list[dict[str, Any]]:
        return self.auth.list_keys()

    def auth_revoke_key(self, key_id: str) -> bool:
        return self.auth.revoke_key(key_id)

    def auth_grant(self, key_id: str, hive: str, role: str = "read") -> bool:
        return self.auth.grant(key_id, hive, role)

    def auth_revoke_access(self, key_id: str, hive: str) -> bool:
        return self.auth.revoke(key_id, hive)

    def auth_authenticate(self, key: str) -> dict[str, Any] | None:
        return self.auth.authenticate(key)

    def auth_check(self, bearer: str | None,
                   hive: str, role: str = "read") -> dict[str, Any] | None:
        if not bearer:
            return None
        key_info = self.auth.authenticate(bearer)
        if not key_info:
            return None
        if self.auth.check_access(key_info, hive, role):
            return key_info
        return None

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def get_vector_store(self, hive_id: str) -> VectorStore | None:
        kg = self.federation.get_graph(hive_id)
        if not kg:
            return None
        return VectorStore(kg)

    def embed_hive(self, hive_id: str) -> dict[str, Any]:
        vs = self.get_vector_store(hive_id)
        if not vs:
            raise ValueError(f"Hive '{hive_id}' not found")
        count = vs.compute_all()
        return {"hive": hive_id, "embedded": count, "stats": vs.stats()}

    def vector_similar(self, hive_id: str, text: str,
                       top_k: int = 10,
                       metric: str = "cosine") -> list[dict[str, Any]]:
        vs = self.get_vector_store(hive_id)
        if not vs or not vs.has_vectors():
            return []
        return vs.similar_to_text(text, top_k=top_k, metric=metric)

    # ------------------------------------------------------------------
    # Collections
    # ------------------------------------------------------------------

    def compare_hives(self, hive_ids: list[str]) -> dict[str, Any]:
        return self.federation.compare_hives(hive_ids)

    def create_collection(self, name: str, description: str = "") -> dict[str, Any]:
        return self.federation.create_collection(name, description)

    def list_collections(self) -> list[dict[str, Any]]:
        return self.federation.list_collections()

    def get_collection(self, cid: str) -> dict[str, Any]:
        return self.federation.get_collection(cid)

    def delete_collection(self, cid: str) -> None:
        return self.federation.delete_collection(cid)

    def add_hive_to_collection(self, cid: str, hive_id: str) -> dict[str, Any]:
        return self.federation.add_hive_to_collection(cid, hive_id)

    def remove_hive_from_collection(self, cid: str, hive_id: str) -> dict[str, Any]:
        return self.federation.remove_hive_from_collection(cid, hive_id)

    def stats(self) -> dict[str, Any]:
        return self.federation.stats()
