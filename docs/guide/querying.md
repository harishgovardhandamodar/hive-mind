---
description: Querying across hives with natural language
icon: arrows-right-left
---

# Querying Across Hives

## Natural language queries

HiveMind understands natural language queries that reference hive names:

```bash
python -m hivemind search "How is Photonic Computing related to AI Acceleration?"
```

The query parser:
1. Identifies hive names mentioned in the text
2. If exactly 2 hives are found, finds the shortest path through the meta-graph
3. If 3+ hives are found, uses them as waypoints
4. Collects cross-edges and concepts from each intermediate hive
5. Returns the combined subgraph with a chain explanation

## How it works

The **multi-hop query** feature traverses the meta-graph to find paths between hives. For example, if `gnns` is linked to `graph-networks` which is linked to `llms`, a query about "gnns and llms" will:

1. Find the path: `gnns → graph-networks → llms`
2. Collect all nodes from the first hive
3. Collect cross-edges between `gnns` and `graph-networks`
4. Collect concepts from `graph-networks`
5. Collect cross-edges between `graph-networks` and `llms`
6. Collect all nodes from the last hive

The response includes a `chain` field showing the traversal path.

## Dashboard

In the dashboard, type a query like:

```
How is Photonic computing related to AI acceleration?
```

Into the search bar and click **Ask**. The graph view updates to show the relevant subgraph, and the explanation panel describes the path.

## API

```bash
curl "http://127.0.0.1:9090/api/query?q=How+is+GNNs+related+to+LLMs?"
```

Returns:

```json
{
  "source": "gnns",
  "target": "llms",
  "chain": ["gnns", "graph-networks", "llms"],
  "nodes": [...],
  "edges": [...],
  "explanation": "Path: gnns → graph-networks → llms"
}
```
