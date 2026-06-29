# HiveMind — Recommendations

## Critical gaps

### No test suite
2755 lines of Python with zero tests. Every refactor or feature addition risks regressions.

**Recommendation**: Start with pytest. Cover the three core paths:
- `KnowledgeGraph` — add/remove/search nodes and edges, save/load/backup round-trips
- `Federation` — cross-hive linking, unified search scoring, multi-hop query BFS
- `ConceptIngester` — keyword extraction, arXiv import parsing, concept resolution

```bash
pip install pytest pytest-cov
# tests/test_knowledge_graph.py, tests/test_federation.py, tests/test_ingester.py
```

### Single-threaded HTTP server
`http.server.HTTPServer` blocks on every request. SSE clients consume a thread each. Under load the server becomes unresponsive.

**Recommendation**: Swap to a lightweight async server. Minimal lift is `http.server.ThreadingHTTPServer` (stdlib, Python 3.7+). Better options:

| Server | Effort | Benefit |
|---|---|---|
| `ThreadingHTTPServer` | 2 lines | Handles concurrent requests |
| `uvicorn` + `Starlette` | medium | Real async, WebSocket support, lifespan events |
| `aiohttp` | medium | Native async, WebSocket, client for arXiv |

If keeping stdlib, replace `HTTPServer` with `ThreadingHTTPServer` and move SSE to a separate polling endpoint using `Queue`.

### No logging
`log_message` is a no-op. Debugging production issues requires reading raw print output.

**Recommendation**: Replace `print()` with `logging` throughout:

```python
import logging
logger = logging.getLogger("hivemind")

# In server.py, restore log_message to use logging
def log_message(self, fmt, *args):
    logger.info(fmt % args)
```

Add `--verbose` / `-v` flag for debug-level logging.

### Backups are unbounded
Every `save()` copies the full graph. 100 saves = 100 full copies. On large hives this fills disk fast.

**Recommendation**: Add a retention policy:
- Keep last N backups (default 20)
- Keep one per day for older than 7 days
- Add `hivemind backup prune --keep 20` command

## Performance

### JSON serialization of the full graph
`save()` calls `nx.node_link_data()` + `json.dump()` on every write. For hives with 10k+ nodes this takes seconds.

**Recommendation**: Keep the JSON format for human readability and git-friendliness, but batch writes:
- Debounce saves: accumulate changes for 1s before writing (configurable)
- Or switch to SQLite via `sqlite3` stdlib for the active graph, export to JSON on demand

SQLite sketch:
```python
CREATE TABLE nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, data JSON);
CREATE TABLE edges (source TEXT, target TEXT, relation TEXT, cross_graph INT, target_graph TEXT);
```

This enables incremental updates, efficient queries (find all edges for a node without loading everything), and concurrent readers.

### TF-IDF recomputed on every search
`unified_search()` builds term frequencies from scratch each time.

**Recommendation**: Cache the inverted index:
- Rebuild when a hive is saved
- Store in a `data/search_index.json` alongside the meta-graph
- Invalidate on hive save (triggered via the existing backup hook)

### Vector embeddings stored as flat JSON
384-dim floats × 1000 nodes = ~3MB of JSON. Parsing this on every server start is wasteful.

**Recommendation**: Store embeddings in a `.npy` file (NumPy binary format, 10× smaller, instant load). Use `numpy` only for storage, keep `sentence-transformers` optional.

```python
import numpy as np
# Save
np.save(path, {"ids": list(vectors.keys()), "embeddings": list(vectors.values())})
# Load
data = np.load(path, allow_pickle=True).item()
```

## Data quality

### No concept normalization across hives
"Graph Neural Network" in `gnns` and "graph neural network" in `graph-networks` are separate concepts. No cross-hive dedup or linking.

**Recommendation**: Add a `hivemind link-concepts` / `POST /api/link-concepts` that:
1. Compares concept labels using vector similarity across all hives
2. Suggests candidate matches above a threshold
3. Creates cross-graph edges for confirmed matches

This could run as a scheduled background task or be triggered manually.

### No concept hierarchy
Concepts are flat — no parent/child, broader/narrower relationships.

**Recommendation**: Add a `broader` / `narrower` relation alongside `related_to`. Detect hierarchy from:
- Label substring containment ("Attention" ⊆ "Self-Attention")
- Embedding clustering
- Manual curation via CLI flag

### arXiv metadata is sparse
Only title, authors, abstract, and categories are stored. Missing: DOI, citation count, venue, publication year as a structured field.

**Recommendation**: Fetch additional metadata from CrossRef or Semantic Scholar APIs. `crossref-commons` is lightweight and free. Extend the arXiv import flow with an optional `--enrich` flag.

## Dashboard

### Graph visualization is read-only
Users can't edit nodes, add edges, or reposition nodes from the UI. All mutations require the CLI or API.

**Recommendation**: Add these UI affordances:
- **Double-click** on empty space → create concept node
- **Drag from node → node** → create edge (with relation picker)
- **Right-click menu** → delete node, edit label
- **Persist layout**: save node positions to a `layout.json` per hive

### No zoom controls
D3.js force layout has no built-in zoom UI. Users on small screens can't navigate dense graphs.

**Recommendation**: Add D3 zoom behavior with mouse wheel and a zoom slider. Minimum viable:

```javascript
const zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", (e) => svg.attr("transform", e.transform));
svg.call(zoom);
```

### No mobile support
The dashboard doesn't work on phones.

**Recommendation**: At minimum, make the sidebar collapsible and increase touch target sizes. A responsive CSS breakpoint at 768px would cover tablets.

### Search results don't show score
The dashboard renders search results without the TF-IDF score.

**Recommendation**: Add the `score` field to the result HTML. Sort by score descending.

## API

### No pagination
`/api/search` returns `results[:50]` — arbitrary cutoff. `/api/hive/<id>` returns all nodes/edges without limits.

**Recommendation**: Add `?limit=50&offset=0` or `?cursor=...` to list endpoints. Return `total` in the response.

### No CORS configuration
`Access-Control-Allow-Origin: *` is hardcoded. Fine for dev, not for production.

**Recommendation**: Make CORS configurable:

```yaml
server:
  cors_origins:
    - https://my-dashboard.com
```

### No request validation
Malformed JSON returns 500 or ambiguous errors.

**Recommendation**: Use Pydantic or a simple schema validation in each endpoint handler.

## CLI

### No tab completion
Typing `python -m hivemind <TAB>` yields nothing.

**Recommendation**: Generate shell completion scripts. `argparse` supports this via `argparse.ArgumentParser.print_help()`. Third-party options:

```bash
# Install shtab
pip install shtab
python -m hivemind --print-completion bash > /etc/bash_completion.d/hivemind
```

### No colored output
CLI output is plain white text. Difficult to scan.

**Recommendation**: Use `rich` or a simple ANSI color wrapper:

```python
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
```

Color status icons (✓/~/) and highlight hive names in output.

### arXiv import has no progress bar
`import_from_arxiv()` prints nothing for minutes during a large import.

**Recommendation**: Use `tqdm` for progress:

```python
from tqdm import tqdm
for arxiv_id in tqdm(arxiv_ids, desc="Fetching papers"):
    ...
```

Keep `tqdm` optional (try/except ImportError).

## Developer experience

### No pre-commit hooks
Code style and basic checks aren't enforced.

**Recommendation**: Set up `pre-commit`:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.0
    hooks:
      - id: black
  - repo: https://github.com/astral-sh/ruff
    rev: 0.3.0
    hooks:
      - id: ruff
```

Run `pre-commit install` once. Add a `make fmt` command.

### Makefile or task runner
No canonical way to install, test, lint, format, or run.

**Recommendation**: Add a `Makefile`:

```makefile
.PHONY: install test lint fmt run

install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt  # pytest, ruff, black, pre-commit

test:
	pytest -v --cov=hivemind

lint:
	ruff check hivemind/

fmt:
	black hivemind/

run:
	python -m hivemind serve
```

### No changelog
No way to know what changed between versions.

**Recommendation**: Add `CHANGELOG.md` following [Keep a Changelog](https://keepachangelog.com/). Use `git-cliff` or similar to auto-generate from commit messages.

## Architecture

### HiveMind class is a god object
`hive_mind.py` has 20+ methods spanning auth, export, embeddings, backups, queries. Hard to test and maintain.

**Recommendation**: Decompose into focused service classes:
- `HiveService` — CRUD for hives, linking
- `SearchService` — unified search, query relation
- `BackupService` — history, diff, rollback
- `AuthService` → already extracted as `AccessControl`
- Keep `HiveMind` as a thin facade that wires them together

### Config is global and mutable
`config = load_config()` is called in multiple places. Modules read from a dict with no validation.

**Recommendation**: Make `config` a frozen dataclass:

```python
@dataclass(frozen=True)
class Config:
    hives_dir: Path = Path("hives")
    meta_graph_path: Path = Path("data/meta_graph.json")
    server_host: str = "127.0.0.1"
    server_port: int = 9090
```

Pass it explicitly to constructors instead of reading from a global.

### No health check endpoint
No way for Docker/load balancers to know if the server is alive.

**Recommendation**: Add `GET /api/health` that returns `{"status": "ok", "hives": 11}`.

## Feature ideas

### WebSocket (full duplex)
SSE only pushes server→client. WebSocket would enable:
- Real-time graph editing from the dashboard
- Collaborative editing
- Push notifications when imports complete

**Recommendation**: When migrating to async server, add WebSocket support via `starlette.websockets` or similar.

### RDF/Turtle export
JSON-LD is done but Turtle/N-Triples are more widely used in the semantic web community.

**Recommendation**: Add `export_hive(..., fmt="turtle")` using `rdflib` (or hand-roll a simple serializer — Turtle syntax is straightforward).

### GraphQL API
REST endpoints proliferate. A GraphQL API would let clients query exactly what they need.

**Recommendation**: Add a Strawberry/GraphQL-core endpoint alongside REST. Single `query { hive(name: "transformers") { papers { title concepts { label } } } }`.

### Citation graph traversal
Papers cite other papers. Currently no citation edges are imported.

**Recommendation**: Extend arXiv import to fetch references from the arXiv API or Semantic Scholar. Add `cites` / `cited_by` edge types. Enable forward/backward citation traversal.

### Language detection for concepts
Concepts are currently English-only. Keywords extracted from foreign-language abstracts would be garbage.

**Recommendation**: Add `langdetect` or `fasttext` language detection. Skip non-English abstracts or translate with a note.

### Periodic re-embedding
New concepts get embeddings, but existing ones don't change. If the embedding model is updated, old vectors are stale.

**Recommendation**: Add `hivemind embed --refresh` that regenerates all embeddings from scratch. Add a `generated_at` timestamp to `embeddings.json`.

## Priority matrix

| Item | Impact | Effort | Suggested order |
|---|---|---|---|
| Test suite | Critical | Medium | 1 |
| `ThreadingHTTPServer` | High | Low | 2 |
| Logging | High | Low | 3 |
| Backup retention | Medium | Low | 4 |
| Search result scores in UI | Medium | Low | 5 |
| Zoom controls | Medium | Low | 6 |
| Tab completion | Low | Low | 7 |
| Colored CLI output | Low | Low | 8 |
| Pre-commit + CI | Medium | Low | 9 |
| Changelog | Medium | Low | 10 |
| Cross-hive concept linking | High | Medium | 11 |
| SQLite backend | High | Large | 12 |
| Async server | High | Large | 13 |
| UI graph editing | Medium | Large | 14 |
| Citation traversal | Medium | Medium | 15 |
