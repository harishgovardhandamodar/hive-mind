---
description: The Federation and meta-graph
icon: arrow-right-arrow-left
---

# Federation

The `Federation` class manages all hives and provides cross-graph operations.

## Meta-graph

A lightweight `MultiDiGraph` where:

- **Nodes** are hives (referenced by graph ID)
- **Edges** are links between hives

The meta-graph is stored in `data/meta_graph.json` and persisted as JSON.

## Registration

Hives are discovered automatically by scanning the `hives/` directory for `knowledge_graph.json` files. They can also be registered programmatically via `register_graph()`.

## Cross-graph edges

When two concepts in different hives are connected, the edge is stored in the source hive's graph with:

```json
{
  "source": "concept:GNN",
  "target": "concept:GraphNetwork",
  "relation": "related_to",
  "cross_graph": true,
  "target_graph": "graph-networks"
}
```

These appear in the dashboard as dashed yellow lines.

## Multi-hop queries

When a user types a natural language query mentioning hive names (e.g., "How is GNNs related to LLMs?"), the federation:

1. Identifies hive names using case-insensitive matching against registered graph IDs
2. If exactly 2 hives are found, runs BFS on the meta-graph to find the shortest path
3. If 3+ hives are found, uses them as waypoints
4. Collects all nodes from the source and target hives
5. Collects cross-edges and concept nodes from intermediate hives
6. Returns the combined subgraph with a human-readable explanation

## Unified search

`unified_search()` scores all nodes across all hives using TF-IDF with an exact-match bonus. Results include the `graph_id` so you can see which hive each result belongs to.
