---
description: Importing papers from the arXiv API
icon: cloud-arrow-down
---

# Importing from arXiv

Import papers by arXiv ID to automatically create paper nodes, extract concepts, and link everything:

```bash
python -m hivemind arxiv-import 1706.03762 2006.16236 --hive transformers
```

## What happens

1. HiveMind fetches paper metadata from the arXiv API (title, authors, abstract, categories)
2. Creates a `paper` node for each paper
3. Extracts keywords from the title and abstract using heuristic scoring
4. Creates `concept` nodes for each extracted keyword
5. Creates `introduces` edges from the paper to each concept
6. Resolves each new concept against existing papers (creates `related_to` edges)
7. Saves the knowledge graph

## Controlling concept extraction

```bash
python -m hivemind arxiv-import 1706.03762 --hive gnns --max-concepts 5
```

Limits extraction to the top 5 keywords per paper.

## Skip resolution

```bash
python -m hivemind arxiv-import 1706.03762 --hive gnns --no-resolve
```

Skips linking extracted concepts to existing papers.

## Target hive

If the target hive doesn't exist, it is created automatically:

```bash
python -m hivemind arxiv-import 2306.07944 --hive speech
```

## Batch size

arXiv API requests are batched in groups of 50 IDs with a 300ms throttle between requests to comply with rate limits.
