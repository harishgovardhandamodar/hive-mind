---
description: Vector embeddings for semantic search
icon: brain
---

# Embed

## Generate embeddings

```bash
python -m hivemind embed transformers
```

This generates vector embeddings for all concept and paper nodes in the hive. The first run downloads the `all-MiniLM-L6-v2` model (~80MB).

Output:

```
Embedded 49 nodes in hive 'transformers'
  Backend: sentence-transformers
  Dims:    384
```

## Semantic search

```bash
python -m hivemind embed transformers --query "sequence to sequence model"
```

This returns concepts and papers ranked by cosine similarity to the query text:

```
Top matches for 'sequence to sequence model' in hive 'transformers':
Node                                 Type       Similarity
--------------------------------------------------------
concept:Self-Attention               concept       0.7580
concept:attention                    concept       0.6465
concept:self-attention               concept       0.6215
```

## How it works

- Primary backend: `sentence-transformers` with `all-MiniLM-L6-v2` (384-dim)
- Fallback: character n-gram TF-IDF with feature hashing (128-dim)
- Embeddings are stored in `hives/<name>/data/graph/embeddings.json`
- Auto-embedding: new concepts are embedded automatically on ingest
- The `find_similar()` method uses vector search when embeddings exist

## Integrating with find_similar

When vector embeddings are available, `find_similar()` uses them as the primary matching strategy, falling back to fuzzy string matching only if no vectors exist.
