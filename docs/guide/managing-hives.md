---
description: Create, inspect, link, and manage hives
icon: hexagon-layers
---

# Managing Hives

## Create a hive

```bash
python -m hivemind init quantum-computing
```

This creates a `hives/quantum-computing/` directory with a `data/graph/knowledge_graph.json` file.

## List all hives

```bash
python -m hivemind list
```

## Inspect a hive

```bash
python -m hivemind inspect transformers
```

Shows papers, concepts, graph refs, cross-graph edges, and connected hives.

## Link hives

Link two hives to enable cross-hive queries:

```bash
python -m hivemind link gnns graph-networks --relation extends
```

This adds an edge to the meta-graph (not to individual knowledge graphs).

## Connect concepts across hives

```bash
python -m hivemind connect gnns concept:GNN graph-networks concept:GraphNetwork --relation related_to
```

This creates a cross-graph edge between two concepts in different hives — visible in the dashboard as a dashed yellow line.
