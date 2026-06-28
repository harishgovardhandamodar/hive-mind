# HiveMind Improvements

## Near-term

- **Paper detail tooltip**: node hover already shows type/hive — add abstract popup for paper nodes with link to arxiv
- **Cross-edge visualization**: show cross-graph edges in the Unified view as dashed lines (currently only meta-graph uses dashes)
- **Ingest feedback**: add success toast / animation in the dashboard when a concept is added, rather than just text in the panel
- **Validation**: warn when adding a concept that already exists in *any* hive (ingest already skips on match, but the UI could show a clearer preview)

## Medium-term

- **Named-entity recognition**: improve `extract_keywords()` with a lightweight POS tagger or integrate `spaCy` as an optional backend for proper noun phrase extraction from abstracts
- **Concept resolution**: link auto-added concepts to papers in the same hive that mention them (scan titles/abstracts for matches)
- **Graph diff/rollback**: track changes to each `knowledge_graph.json` so users can undo bulk imports
- **Bulk import from arxiv**: fetch papers by arxiv IDs, extract concepts, and populate — combine `ingest` with the existing `import-from-obsidian` flow
- **Search ranking**: `unified_search()` currently does substring match — add TF-IDF or embedding-based ranking for better results

## Long-term

- **Vector embeddings**: store concept embeddings (e.g. via `sentence-transformers`) in each hive to enable semantic concept matching and better `find_similar()`
- **Multi-hop query reasoning**: extend `query_relation()` to follow paths across 3+ hives via meta-graph traversal, not just source↔target pairs
- **WebSocket live sync**: push hive updates to the dashboard in real time without page reload
- **Access control**: multi-user with read/write permissions per hive (useful for collaborative knowledge graph curation)
- **Export formats**: serialize subgraphs as JSON-LD, RDF/Turtle, or Obsidian-compatible markdown

## Quick wins

- Add `--dry-run` flag to `hivemind ingest` that shows what *would* be added without actually writing
- Normalize concept labels on save (trim, collapse whitespace, title-case)
- Add `docker compose up` instructions to a comment in `config.yaml`
- The landing page (`index.html`) could link to the dashboard
