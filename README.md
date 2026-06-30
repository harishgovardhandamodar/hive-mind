# HiveMind

**Federated knowledge graphs for research intelligence.**

HiveMind lets you build, connect, and query topic-specific knowledge graphs ("hives"). Each hive indexes papers, concepts, and their relationships within a domain. Hives are linked through a meta-graph, enabling cross-domain queries and discovery.

```bash
pip install -r requirements.txt
python -m hivemind serve
# → http://127.0.0.1:9090
```

---

## Quick start

```bash
# Create a hive
python -m hivemind init my-hive

# Add a concept
python -m hivemind ingest "Graph Neural Network" --hive gnns

# Import papers from arXiv
python -m hivemind arxiv-import 1706.03762 2006.16236 --hive transformers

# Search across all hives
python -m hivemind search "attention mechanism"

# Launch the dashboard
python -m hivemind serve
```

---

## CLI reference

| Command | Description |
|---|---|
| `init <name>` | Create a new hive |
| `list` | List all hives |
| `inspect <name>` | Show hive details |
| `link <src> <tgt>` | Link two hives |
| `connect <src> <cA> <tgt> <cB>` | Cross-hive concept connection |
| `search <query>` | Unified search |
| `ingest <keyword>` | Add a concept |
| `arxiv-import <ids...>` | Import papers by arXiv ID |
| `export <name>` | Export as JSON-LD or Obsidian |
| `export-data <id>` | Export hive as portable JSON |
| `import-hive <file>` | Import a hive from JSON export |
| `embed <name>` | Generate vector embeddings |
| `history <name>` | Backup versions |
| `diff <name> <version>` | Diff against a backup |
| `rollback <name> <version>` | Restore a backup |
| `auth create-key <name>` | Create an API key |
| `auth grant <id> <hive>` | Grant hive access |
| `peers info` | Show instance identity for pairing |
| `peers invite` | Generate one-time pairing token |
| `peers pair <url>` | Bidirectional pairing (add `--token` for secure pairing) |
| `peers add <url>` | Manually register a peer |
| `peers list` | List known peers |
| `peers remove <id>` | Remove a peer |
| `peers sync <id>` | Pull all hives from a peer |
| `peers pull <id> <hive>` | Pull a specific hive from a peer |
| `serve` | Start the dashboard (use `--cert`/`--key` for TLS) |
| `stats` | Federation statistics |

---

## API endpoints

**Base**: `http://127.0.0.1:9090`

### GET

| Path | Description |
|---|---|
| `/` | Dashboard |
| `/api/stats` | Federation stats |
| `/api/hives` | List hives |
| `/api/hive/<id>` | Hive graph data |
| `/api/meta-graph` | Meta-graph |
| `/api/query?q=...` | Natural language query |
| `/api/search?q=...` | Unified search |
| `/api/history?hive=...` | Backup history |
| `/api/export?hive=...` | Export hive |
| `/api/embed?hive=...` | Embeddings / vector search |
| `/api/events` | SSE live stream |
| `/api/auth/keys` | List API keys |

### POST

| Path | Body | Description |
|---|---|---|
| `/api/ingest` | `{keyword, hive, ...}` | Add concept |
| `/api/arxiv-import` | `{ids: [...], hive}` | Import papers |
| `/api/auth/create-key` | `{name}` | Create API key |
| `/api/peers/pair` | `{url, token?}` | Pair with remote instance |
| `/api/peering/invite` | `{}` | Generate pairing invite token |
| `/api/peering/pair` | `{peer_url, token?}` | Accept pairing request |

---

## Architecture

```
CLI → HiveMind → Federation → KnowledgeGraph
                     ↓              ↓
              AccessControl    VectorStore
                     ↓              ↓
              permissions     embeddings.json
```

- **KnowledgeGraph** — A `networkx.MultiDiGraph` per hive, persisted as JSON
- **Federation** — Manages multiple hives, cross-hive edges, and the meta-graph
- **VectorStore** — `sentence-transformers` embeddings for semantic search (384-dim)
- **AccessControl** — API key authentication with per-hive read/write/admin roles
- **ConceptIngester** — Keyword extraction, arXiv import, concept-to-paper resolution
- **Server** — Built-in HTTP server with D3.js dashboard, SSE live sync, and peer-to-peer peering endpoints

---

## Configuration

See `config.yaml`:

```yaml
hives_dir: hives
meta_graph_path: data/meta_graph.json
server:
  host: 127.0.0.1
  port: 9090
```

---

## Docker

```bash
docker compose up -d
# → http://localhost:9090
```

Volumes mount `./hives` and `./data` for persistence.

---

## Data model

**Nodes**: `paper`, `concept`, `graph_ref`  
**Edges**: `related_to`, `introduces`, `references`, `extends`, `uses`, `contradicts`  
**Storage**: JSON (networkx node-link format) per hive, with automatic timestamped backups.

---

## Embeddings

Install `sentence-transformers` for semantic vector search:

```bash
pip install sentence-transformers
python -m hivemind embed transformers
python -m hivemind embed transformers --query "sequence to sequence"
```

Without it, the system falls back to character n-gram TF-IDF.

---

## Access control

API keys grant per-hive access. No auth required until at least one key exists.

```bash
python -m hivemind auth create-key alice
# → ID: abc123, Key: <secret>
python -m hivemind auth grant abc123 transformers --role write
```

Use the key in requests:

```
Authorization: Bearer <key>
```

---

## Export

```bash
# JSON-LD
python -m hivemind export transformers --format jsonld > transformers.jsonld

# Obsidian markdown
python -m hivemind export transformers --format obsidian --output ./vault
```

---

## License

MIT
