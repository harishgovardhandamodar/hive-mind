# HiveMind — Project Suggestions

Scan date: 2026-06-30 · Branch: `feature/hive-sharing`

This document captures actionable recommendations after reviewing the codebase (~4,300 lines of Python, ~490 lines of tests, D3 dashboard, GitBook docs). Items marked **Done** are already implemented; the rest are ordered by impact.

---

## What’s in good shape

Several earlier gaps are already closed:

| Area | Status |
|---|---|
| Test suite (KnowledgeGraph, Federation, ConceptIngester) | **Done** — ~50 tests in `tests/` |
| Concurrent HTTP server | **Done** — `ThreadingHTTPServer` in `server.py` |
| Structured logging | **Done** — `logging` in core modules; `log_message` wired to logger |
| Backup retention | **Done** — `max_backups` (default 20) with `_prune_backups()` |
| Semantic search | **Done** — optional `sentence-transformers` + TF-IDF fallback |
| Access control | **Done** — API keys with per-hive roles |
| Live dashboard updates | **Done** — SSE event bus |
| Hive sharing / peering | **Done** — pairing tokens, bidirectional sync, CLI + API |
| Hive collections | **Done** — CLI + API + dashboard tab |
| Dashboard UX | **Done** — zoom, paper tooltips, ingest toasts, cross-edge dashes |

Use this as the baseline; focus new work on the gaps below.

---

## 1. Security & federation (high priority)

### 1.1 Protect peering and admin endpoints

**Problem:** Auth is enforced only on `/api/ingest` and `/api/arxiv-import`. These are currently open to anyone who can reach the server:

- `GET /api/peering/hive/<id>` — full hive export
- `GET /api/peering/hives` — hive inventory
- `POST /api/peers/<id>/sync` — pull remote data
- `GET /api/auth/keys`, `POST /api/auth/create-key`, `POST /api/auth/grant`
- `GET /api/rollback` — destructive restore via GET

**Instructions:**

1. Add a global `require_auth` mode once any API key exists (mirror ingest behavior).
2. Require at least `read` role for peering export endpoints; `admin` for auth management and rollback.
3. For peering specifically, consider a separate **federation token** (long-lived, scoped to export/sync) distinct from user API keys.
4. Change rollback to `POST /api/rollback` with body `{hive, version}` — never mutate state on GET.
5. Document the threat model in `docs/architecture/access-control.md` and `docs/guide/peer-pairing.md`.

### 1.2 Harden pairing tokens

**Problem:** Used invite tokens live in an in-memory `_used_tokens` set (`federation.py`). A server restart allows token replay.

**Instructions:**

1. Persist consumed tokens to `data/used_invites.json` (or store hash + expiry in `peers.json`).
2. Add optional IP / rate limiting on `/api/peering/pair` (even a simple in-memory counter helps).
3. Require TLS (`--cert`/`--key`) in production docs; keep token requirement for non-TLS as today.

### 1.3 Fix default admin key behavior

**Problem:** `AccessControl._load()` auto-creates a default admin key and logs it once. This is convenient for dev but risky if logs are shared or the server starts exposed.

**Instructions:**

1. Gate auto-key creation behind `config.yaml`: `auth.auto_create_admin: false` (default false in production examples).
2. Add `hivemind auth bootstrap` CLI command for explicit first-time setup.
3. Never log the raw key at WARNING level in production; print once to stdout only when `--bootstrap` is passed.

### 1.4 Make CORS configurable

**Problem:** `Access-Control-Allow-Origin: *` is hardcoded on every response.

**Instructions:**

```yaml
# config.yaml
server:
  cors_origins:
    - http://localhost:9090
    - https://my-dashboard.example.com
```

Default to same-origin or empty (no CORS header) when unset.

---

## 2. Testing & CI

### 2.1 Make tests runnable out of the box

**Problem:** Tests exist but `pytest` is not in `requirements.txt` or a dev extras file. Running `python3 -m pytest` fails on a fresh clone.

**Instructions:**

1. Add `requirements-dev.txt`:

   ```
   pytest>=8.0
   pytest-cov>=5.0
   ruff>=0.4
   ```

2. Add a one-liner to README: `pip install -r requirements-dev.txt && pytest`.

### 2.2 Expand test coverage

**Current gaps** (no tests found for):

| Module | Suggested tests |
|---|---|
| `federation.py` (peering) | `pair_with_peer`, `verify_invite`, token replay, `pull_peer_hives` |
| `federation.py` (collections) | create/list/add/remove hive membership |
| `auth.py` | role checks, grant/revoke, empty-hives = admin |
| `embeddings.py` | TF-IDF fallback path, cosine similarity ranking |
| `server.py` | handler auth matrix, JSON validation, 404 paths |

Use `unittest.mock` / `responses` for HTTP peering calls; temp dirs for graph I/O (pattern already in existing tests).

### 2.3 Add GitHub Actions CI

**Instructions:** Create `.github/workflows/test.yml`:

```yaml
name: test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest -v --cov=hivemind --cov-report=term-missing
      - run: ruff check hivemind/
```

Add badge to README when live.

---

## 3. Packaging & developer experience

### 3.1 Publish as an installable package

**Problem:** No `pyproject.toml`, `setup.py`, or `LICENSE` file. Users must clone and `pip install -r requirements.txt`.

**Instructions:**

1. Add `pyproject.toml` with `[project]` name `hivemind`, entry point `hivemind = hivemind.cli:main`.
2. Add `LICENSE` (MIT, as stated in README).
3. Add `CHANGELOG.md` (Keep a Changelog format).
4. Pin optional extras: `pip install hivemind[embeddings]` → `sentence-transformers`.

### 3.2 Add Makefile or task runner

```makefile
.PHONY: install test lint fmt run

install:
	pip install -r requirements.txt -r requirements-dev.txt

test:
	pytest -v --cov=hivemind

lint:
	ruff check hivemind/ tests/

fmt:
	ruff format hivemind/ tests/

run:
	python -m hivemind serve
```

### 3.3 Pre-commit hooks

Add `.pre-commit-config.yaml` with `ruff` (lint + format). Keeps the growing codebase consistent without debate.

### 3.4 Shell tab completion

Add optional `shtab` integration in `cli.py`:

```bash
python -m hivemind --print-completion bash > ~/.local/share/bash-completion/completions/hivemind
```

---

## 4. Configuration & deployment

### 4.1 Remove machine-specific paths from committed config

**Problem:** `config.yaml` and `docker-compose.yml` reference `/home/fox/hive-data/hives`. This breaks for other developers and CI.

**Instructions:**

1. Commit `config.yaml.example` with relative paths (`hives_dir: hives`).
2. Use env var overrides in `config.py`:

   ```python
   config["hives_dir"] = os.environ.get("HIVEMIND_HIVES_DIR", config["hives_dir"])
   ```

3. In `docker-compose.yml`, use named volumes or `./hives:/app/hives` instead of absolute host paths.

### 4.2 Typed, validated config

**Problem:** Config is a mutable dict loaded in multiple places with no schema validation.

**Instructions:**

1. Replace with a frozen `@dataclass` or Pydantic `Settings` model.
2. Validate on load: port range, path existence, `max_backups >= 1`.
3. Pass `Config` explicitly into `HiveMind`, `AccessControl`, and `serve()` instead of re-calling `load_config()`.

### 4.3 Health check endpoint

Add `GET /api/health`:

```json
{"status": "ok", "hives": 11, "peers": 2, "uptime_s": 3600}
```

Wire into Docker `HEALTHCHECK` and load balancers.

### 4.4 Docker improvements

- Copy `config.yaml.example` and document env vars in `docs/advanced/docker.md`.
- Add `sentence-transformers` as an optional Docker stage or documented build arg.
- Mount `data/` and hives dir consistently; ensure `permissions.json` path is inside the mounted volume.

---

## 5. Architecture & code organization

### 5.1 Split the monolithic HTTP handler

**Problem:** `server.py` (~700 lines) mixes routing, auth, peering, collections, static files, and SSE.

**Instructions:**

1. Extract route tables: `routes/api.py`, `routes/peering.py`, `routes/static.py`.
2. Or migrate to **Starlette** / **FastAPI** for declarative routes, middleware (auth, CORS, logging), and automatic OpenAPI docs.
3. Keep `HiveMind` as facade but move backup/search/embed logic into focused services (`SearchService`, `BackupService`, `PeerService`).

### 5.2 Split `federation.py`

At ~1,100 lines it handles meta-graph, search, collections, peering, and import. Extract:

- `peering.py` — instance identity, pairing, pull/sync
- `collections.py` — hive grouping
- Keep cross-graph search and meta-graph in `Federation`

### 5.3 Unify API naming

Two parallel namespaces exist: `/api/peers/*` (local registry + sync) and `/api/peering/*` (remote-facing export). This is documented but confusing.

**Instructions:**

1. Document clearly in `docs/api/endpoints.md` which side initiates each call.
2. Long-term: collapse under `/api/v1/federation/...` with consistent verbs.
3. Generate an OpenAPI 3 spec from route definitions for client codegen.

---

## 6. Performance & storage

### 6.1 Debounce or batch graph saves

Every `kg.save()` serializes the full NetworkX graph and creates a backup. Bulk arXiv import triggers many saves.

**Instructions:**

1. Add `KnowledgeGraph.save(debounce=False)` or a context manager `with kg.batch():` that saves once at exit.
2. Expose `max_backups` and debounce interval in `config.yaml`.

### 6.2 Cache search indexes

`unified_search()` rebuilds scoring structures on each query.

**Instructions:**

1. Build inverted index on hive save; store in `data/search_index.json` or per-hive sidecar.
2. Invalidate on `save()` / SSE `hive-update`.

### 6.3 Store embeddings in binary format

Embeddings live in `embeddings.json` (~3 MB per 1k nodes). Parsing on every server start is slow.

**Instructions:**

1. Save as `.npy` + `ids.json` sidecar (NumPy is likely already present via sentence-transformers).
2. Add `hivemind embed --refresh` with `generated_at` timestamp in metadata.
3. Keep JSON export as optional for debugging.

### 6.4 SQLite backend (long-term)

For hives with 10k+ nodes, full JSON load/save becomes a bottleneck. A SQLite adapter behind the same `KnowledgeGraph` interface enables incremental updates and indexed lookups without loading the entire graph.

---

## 7. Data quality & research features

### 7.1 Cross-hive concept linking

Duplicate concepts across hives ("Graph Neural Network" vs "graph neural network") are not auto-linked despite embeddings support.

**Instructions:**

1. Add `hivemind link-concepts --threshold 0.85 --dry-run`.
2. Add `POST /api/link-concepts` returning candidate pairs with similarity scores.
3. Surface suggestions in the dashboard before creating cross-graph edges.

### 7.2 Citation graph import

Papers have metadata but no `cites` / `cited_by` edges from external sources.

**Instructions:**

1. Extend arXiv import with optional `--enrich` using Semantic Scholar or OpenAlex (free APIs).
2. Store DOI, year, venue as structured fields on paper nodes.

### 7.3 Concept hierarchy

`VALID_RELATIONS` includes `nests` but hierarchy detection is manual.

**Instructions:**

1. Auto-suggest `broader`/`narrower` from label containment and embedding clustering.
2. Allow manual override via CLI: `hivemind connect ... --relation nests`.

### 7.4 Language detection

Non-English abstracts produce poor keyword extraction.

**Instructions:** Add optional `langdetect` step in `extract_keywords()`; skip or flag non-English text.

---

## 8. Dashboard & frontend

### 8.1 Modularize the UI

**Problem:** `hivemind/web/index.html` is ~1,600 lines (HTML + CSS + JS in one file). Hard to test and review.

**Instructions:**

1. Split into `web/js/graph.js`, `web/js/peers.js`, `web/css/theme.css`.
2. Or adopt a minimal build step (Vite + vanilla JS) while keeping zero runtime deps for the default install.
3. Pin D3 version locally instead of CDN for offline/air-gapped use.

### 8.2 Interactive graph editing

Node drag repositions locally but layout is not persisted. No create/delete edge from UI.

**Instructions:**

1. Double-click canvas → create concept (call `/api/ingest`).
2. Shift-drag between nodes → relation picker → `POST /api/connect` (new endpoint).
3. Save layout to `hives/<id>/data/graph/layout.json`; restore on load.

### 8.3 Mobile / responsive layout

Viewport meta tag exists but no `@media` breakpoints. Sidebar consumes horizontal space on tablets.

**Instructions:**

1. Collapsible sidebar below 768px.
2. Larger touch targets for peer sync buttons and search.

### 8.4 Search results UX

Scores appear in ingest preview but not consistently in the main search panel.

**Instructions:** Show `score` badge on each result; sort descending; optional filter by hive/collection.

---

## 9. API design

### 9.1 Pagination

`/api/search` truncates at 50; `/api/hive/<id>` returns the full graph.

**Instructions:**

```http
GET /api/search?q=...&limit=50&offset=0
→ {"total": 142, "results": [...]}

GET /api/hive/<id>?limit=500&offset=0&types=paper,concept
```

### 9.2 Request validation

Malformed JSON sometimes returns generic errors. Adopt Pydantic models (if moving to Starlette) or a small `validate_body(schema, data)` helper per route.

### 9.3 Versioned API

Prefix new routes with `/api/v1/` before external clients depend on current paths.

---

## 10. Documentation & repo hygiene

### 10.1 Keep docs in sync with features

Collections and peering are implemented but should be cross-linked from:

- `README.md` CLI table (collections commands)
- `docs/SUMMARY.md` navigation
- `docs/getting-started/quickstart.md` (optional peering walkthrough)

### 10.2 Consolidate recommendation docs

Three overlapping files exist:

| File | Role |
|---|---|
| `improvements.md` | Completed feature checklist |
| `docs/advanced/recommendations.md` | Older audit (some items now stale) |
| `suggestions.md` | This file — current recommendations |

**Instructions:**

1. Archive or update `docs/advanced/recommendations.md` to reference this file and mark resolved items.
2. Move `skill.md` (GitBook editor skill) out of repo root or into `.cursor/skills/` — it is unrelated to HiveMind runtime.

### 10.3 Optional dependencies matrix

Document in README and `docs/getting-started/installation.md`:

| Extra | Package | Enables |
|---|---|---|
| embeddings | `sentence-transformers` | Semantic vector search |
| dev | `pytest`, `ruff` | Tests and lint |
| cli | `rich`, `tqdm` | Colored output, import progress |
| complete | `shtab` | Shell tab completion |

---

## 11. Suggested implementation order

| # | Item | Impact | Effort |
|---|---|---|---|
| 1 | Secure peering + admin endpoints | Critical | Medium |
| 2 | `requirements-dev.txt` + CI | High | Low |
| 3 | Config example + env overrides | High | Low |
| 4 | Health check + Docker HEALTHCHECK | Medium | Low |
| 5 | Persist used pairing tokens | Medium | Low |
| 6 | Tests for peering, auth, collections | High | Medium |
| 7 | `pyproject.toml` + LICENSE | Medium | Low |
| 8 | POST rollback; paginate search | Medium | Low |
| 9 | Cross-hive concept linking | High | Medium |
| 10 | Split server.py / federation.py | Medium | Large |
| 11 | SQLite or debounced saves | High | Large |
| 12 | Dashboard modularization + graph editing | Medium | Large |

---

## 12. Instructions for contributors (template)

Add to `CONTRIBUTING.md` when ready:

1. **Setup:** `pip install -r requirements.txt -r requirements-dev.txt`
2. **Test:** `pytest` — all tests must pass; add tests for new behavior.
3. **Lint:** `ruff check hivemind/`
4. **Config:** Copy `config.yaml.example` → `config.yaml`; never commit personal paths or `permissions.json`.
5. **Docs:** Update `docs/` and README for any new CLI command or API route.
6. **Security:** New endpoints must declare auth requirements; peering exports require explicit opt-in.
7. **Commits:** Imperative subject, focus on why (`fix peering token replay after restart` not `update federation.py`).

---

*Generated from repository scan. Revisit after major features merge to main.*
