---
description: Data model reference
icon: database
---

# Data Model

## Directory structure

```
hivemind/
  data/
    meta_graph.json              # Federation meta-graph
    permissions.json             # API keys and grants
  hives/
    <hive-name>/
      data/
        graph/
          knowledge_graph.json   # Knowledge graph (node-link format)
          embeddings.json        # Vector embeddings
          backups/               # Timestamped backups
            20260628_231948.json
```

## knowledge_graph.json

Uses `networkx.node_link_data()` format:

```json
{
  "graph_id": "transformers",
  "directed": true,
  "multigraph": true,
  "nodes": [
    {"id": "paper:1706.03762", "type": "paper", "label": "Attention Is All You Need", "arxiv_id": "1706.03762"},
    {"id": "concept:Attention", "type": "concept", "label": "Attention"}
  ],
  "links": [
    {"source": "paper:1706.03762", "target": "concept:Attention", "relation": "introduces"},
    {"source": "concept:Attention", "target": "paper:1706.03762", "relation": "related_to"}
  ]
}
```

## embeddings.json

```json
{
  "dims": 384,
  "vectors": {
    "concept:Attention": [0.023, -0.045, ...],
    "paper:1706.03762": [0.012, 0.033, ...]
  }
}
```

## meta_graph.json

Same node-link format but with hive IDs as nodes:

```json
{
  "directed": true,
  "multigraph": true,
  "nodes": [
    {"id": "gnns"},
    {"id": "graph-networks"},
    {"id": "llms"}
  ],
  "links": [
    {"source": "gnns", "target": "graph-networks", "relation": "references"},
    {"source": "graph-networks", "target": "llms", "relation": "references"}
  ]
}
```

## permissions.json

```json
{
  "abc123": {
    "name": "alice",
    "key": "<64-char-hex>",
    "hives": {
      "transformers": "read",
      "gnns": "write"
    }
  }
}
```
