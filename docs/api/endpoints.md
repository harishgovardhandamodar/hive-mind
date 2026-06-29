---
description: REST API endpoints
icon: brackets-curly
---

# Endpoints

Base URL: `http://127.0.0.1:9090`

## GET endpoints

### `/api/stats`

Federation-wide statistics.

### `/api/hives`

List all hives with paper/concept/edge counts.

### `/api/hive/<id>`

Full graph data for a single hive. Returns nodes (with `arxiv_id`, `authors`, `abstract` for papers; `definition` for concepts) and edges (with `cross_graph` and `target_graph` flags).

### `/api/meta-graph`

Meta-graph node-link data showing hive-to-hive connections.

### `/api/search?q=...`

Unified search across all hives. Returns TF-IDF scored results.

### `/api/query?q=...`

Natural language relation query. Finds meta-graph paths between mentioned hives.

### `/api/suggest-concepts?keyword=...`

Suggests hives for a keyword and finds similar existing concepts.

### `/api/extract-keywords?text=...`

Extracts keywords from a block of text using heuristic scoring.

### `/api/history?hive=...`

Lists backup versions for a hive.

### `/api/rollback?hive=...&version=...`

Restores a hive to a previous backup version.

### `/api/export?hive=...&format=jsonld`

Exports a hive in JSON-LD or Obsidian format.

### `/api/embed?hive=...&query=...`

Generates embeddings or performs vector similarity search.

### `/api/auth/keys`

Lists all API keys (requires admin key).

### `/api/events`

SSE stream for real-time updates.

## POST endpoints

### `/api/ingest`

Add a concept to a hive.

**Body:**

```json
{
  "keyword": "Graph Neural Network",
  "definition": "A neural network that operates on graph structures",
  "hive": "gnns",
  "force": false,
  "dry_run": false,
  "no_resolve": false,
  "text": "Optional: extract keywords from this text instead",
  "connect_to": ["Existing Concept"]
}
```

### `/api/arxiv-import`

Import papers from arXiv by IDs.

**Body:**

```json
{
  "ids": ["1706.03762", "2006.16236"],
  "hive": "transformers",
  "max_concepts": 10,
  "no_resolve": false
}
```

### `/api/auth/create-key`

Create a new API key.

**Body:**

```json
{
  "name": "alice"
}
```

### `/api/auth/revoke`

Revoke an API key.

**Body:**

```json
{
  "key_id": "abc123def456"
}
```

### `/api/auth/grant`

Grant hive access to a key.

**Body:**

```json
{
  "key_id": "abc123def456",
  "hive": "transformers",
  "role": "write"
}
```
