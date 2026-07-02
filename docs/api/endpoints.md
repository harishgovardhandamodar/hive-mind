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
  "connect_to": ["Existing Concept"],
  "ollama": false
}
```

When `"ollama": true`, a definition is auto-generated via the local Ollama model
if none is provided.

### `/api/enrich-definitions`

Batch-generate definitions for existing concept nodes using Ollama.

**Body:**

```json
{
  "hive": "gnns",
  "force": false
}
```

Omitting `hive` processes all hives. Set `"force": true` to regenerate definitions
even for concepts that already have one.

**Response:**

```json
{
  "status": "ok",
  "hive": "gnns",
  "updated": 5,
  "skipped": 2,
  "errors": 0
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

## Peering endpoints

### GET `/api/peering/info`

Returns this instance's identity and fingerprint for pairing. Used by remote instances during the pairing handshake.

### GET `/api/peering/hives`

Returns a list of this instance's hives (id, paper/concept/relation counts). Called by peers during sync.

### GET `/api/peering/hive/<id>`

Returns the full exported graph data for a hive. Called by peers during pull/sync.

### POST `/api/peering/invite`

Generate a one-time HMAC-signed pairing token. Optional body: `{"ttl": 600}` (seconds).

**Response:**
```json
{
  "token": "uuid:timestamp:hmac_sig",
  "expires_at": "2025-11-15T12:00:00Z",
  "url": "http://192.168.1.100:9090"
}
```

### POST `/api/peering/pair`

Called by a remote instance during bidirectional pairing. Accepts the remote as a peer. Verifies invite token if provided.

**Body:**
```json
{
  "peer_url": "http://192.168.1.101:9090",
  "peer_name": "server-b",
  "instance_id": "...",
  "fingerprint": "abcd:1234:...",
  "token": "optional-one-time-invite-token"
}
```

## Peer management endpoints

### GET `/api/peers`

List all known peers.

### POST `/api/peers`

Add a peer manually (one-directional).

**Body:**
```json
{
  "url": "http://192.168.1.101:9090",
  "name": "Server B"
}
```

### POST `/api/peers/pair`

Bidirectional pairing with a remote instance. Fetches the remote's info, registers it locally, then registers self on the remote.

**Body:**
```json
{
  "url": "http://192.168.1.101:9090",
  "token": "optional-invite-token"
}
```

### DELETE `/api/peers/<id>`

Remove a peer.

### POST `/api/peers/<id>/sync`

Pull all hives from a peer. Returns import reports with node/edge counts and merge info.

### POST `/api/peers/<id>/pull/<hive_id>`

Pull a specific hive from a peer. Returns same import report format as sync.

## Export/Import endpoints

### GET `/api/hive/<id>/export-data`

Export a hive as portable JSON (node-link format with `hivemind_export` metadata header).

### POST `/api/hives/import`

Import a hive from export data. Supports similarity-based concept merging.

**Body:**
```json
{
  "data": { "hivemind_export": true, "graph": {{...}} },
  "target_name": "optional-new-name",
  "merge_similar": true
}
```
