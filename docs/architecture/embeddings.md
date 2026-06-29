---
description: Vector embeddings for semantic search
icon: brain
---

# Vector Embeddings

The `VectorStore` class manages vector embeddings for nodes in a knowledge graph.

## Backends

### Primary: sentence-transformers

When `sentence-transformers` is installed, HiveMind uses the `all-MiniLM-L6-v2` model to generate 384-dimensional embeddings. This provides high-quality semantic similarity.

### Fallback: char n-gram TF-IDF

If `sentence-transformers` is not available, a character-level 3-gram TF-IDF with feature hashing (128-dim) is used. This is suitable for basic similarity but less accurate than the neural backend.

## Storage

Embeddings are stored in `hives/<name>/data/graph/embeddings.json`:

```json
{
  "dims": 384,
  "vectors": {
    "concept:Self-Attention": [0.023, -0.045, ...],
    "paper:1706.03762": [0.012, 0.033, ...]
  }
}
```

## Integration

- **Auto-embed**: new concepts are embedded automatically on ingest
- **find_similar()**: uses vector search when embeddings exist, falls back to fuzzy/token overlap
- **CLI**: `python -m hivemind embed <hive>` generates embeddings; `--query` searches
- **API**: `GET /api/embed?hive=...` generates; `GET /api/embed?hive=...&query=text` searches

## Cosine similarity

All similarity comparisons use cosine similarity:

```
cosine(a, b) = (a · b) / (||a|| * ||b||)
```
