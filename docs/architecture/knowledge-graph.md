---
description: The KnowledgeGraph data model
icon: diagram-project
---

# Knowledge Graph

Each hive contains a `KnowledgeGraph` — a `networkx.MultiDiGraph` (directed multigraph) stored as JSON.

## Node types

### Paper

Represents a research paper.

```json
{
  "id": "paper:1706.03762",
  "type": "paper",
  "label": "Attention Is All You Need",
  "arxiv_id": "1706.03762",
  "authors": "Vaswani et al.",
  "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
  "published": "2017-06-12",
  "categories": ["cs.CL", "cs.LG"]
}
```

### Concept

A keyword, term, or idea.

```json
{
  "id": "concept:Self-Attention",
  "type": "concept",
  "label": "Self-Attention",
  "definition": "An attention mechanism that computes attention scores between all pairs of positions in a sequence."
}
```

### Graph Ref

A reference to another hive (for cross-hive linking).

```json
{
  "id": "ref:llms",
  "type": "graph_ref",
  "label": "llms",
  "target_graph_id": "llms",
  "relation": "references"
}
```

## Edge types

Edges have a `relation` property:

| Relation | Direction | Meaning |
|---|---|---|
| `related_to` | concept ↔ paper | Concept is discussed in the paper |
| `introduces` | paper → concept | Paper introduces the concept |
| `references` | graph_ref → hive | Hive references another hive |
| `extends` | cross-hive | Concept extends a concept in another hive |
| `uses` | cross-hive | Concept uses a concept in another hive |
| `contradicts` | cross-hive | Concept contradicts a concept in another hive |

Cross-graph edges have `cross_graph: true` and `target_graph` set to the target hive name.

## Persistence

Graphs are serialized using `networkx.node_link_data()` and written as indented JSON. On every `save()`, the previous state is copied to a timestamped backup file.
