---
description: High-level system architecture
icon: sitemap
---

# Architecture Overview

```
CLI (cli.py) ──┐
               ├──> HiveMind (hive_mind.py) ──> Federation (federation.py) ──> KnowledgeGraph (knowledge_graph.py)
Server (server.py) ──┘               │                                          └── VectorStore (embeddings.py)
                                      ├──> AccessControl (auth.py)
                                      └──> ConceptIngester (concept_ingester.py)
                                              └── extract_keywords()
```

## Layers

### Orchestration Layer — `HiveMind`

The top-level class that wires together all components. Provides a unified interface for the CLI and HTTP server. Methods delegate to `Federation`, `AccessControl`, or `ConceptIngester` as appropriate.

### Federation Layer — `Federation`

Manages the collection of `KnowledgeGraph` instances and the meta-graph. Handles cross-hive operations: linking, cross-edges, unified search, multi-hop queries.

### Graph Layer — `KnowledgeGraph`

Wraps a `networkx.MultiDiGraph` persisted as JSON. Each hive has its own graph file. Supports papers, concepts, graph refs, and typed edges.

### Storage Layer

All data is JSON:

| File | Purpose |
|---|---|
| `hives/<name>/data/graph/knowledge_graph.json` | Hive knowledge graph |
| `hives/<name>/data/graph/embeddings.json` | Vector embeddings (optional) |
| `hives/<name>/data/graph/backups/*.json` | Timestamped backups |
| `data/meta_graph.json` | Federation meta-graph |
| `data/permissions.json` | API keys and permissions |
