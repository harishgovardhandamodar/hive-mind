---
description: Searching across all hives
icon: magnifying-glass
---

# Search

## Unified search

```bash
python -m hivemind search "transformer attention"
```

HiveMind searches all hives simultaneously using TF-IDF scoring with an exact-match bonus. Results are ranked by relevance.

## How scoring works

1. Each node's label is compared against the query
2. TF-IDF (Term Frequency-Inverse Document Frequency) scores relevance
3. Exact substring matches get a bonus multiplier
4. Results are sorted by score descending

## Search via API

```bash
curl "http://127.0.0.1:9090/api/search?q=graph+neural+network"
```

Returns:

```json
[
  {
    "graph_id": "gnns",
    "node_id": "concept:Graph Neural Network",
    "label": "Graph Neural Network",
    "type": "concept",
    "score": 8.5
  },
  ...
]
```

## Search via dashboard

The dashboard has a search bar at the top. Type a query and press Enter or click the search icon. Results appear in the right panel. Click a result to navigate to its hive.
