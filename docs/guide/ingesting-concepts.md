---
description: Adding concepts to hives
icon: plus-circle
---

# Ingesting Concepts

## Add a single concept

```bash
python -m hivemind ingest "Differentiable Programming" --hive gnns
```

HiveMind automatically:
1. Checks for similar existing concepts (skips if found and `--force` is not set)
2. Suggests a target hive if none is provided
3. Adds the concept to the knowledge graph
4. Resolves the concept against paper titles/abstracts (links to matching papers)
5. Generates a vector embedding

## Add with a definition

```bash
python -m hivemind ingest "Transformer" \
  --hive transformers \
  --definition "A neural network architecture based on self-attention"
```

## Add from text

Extract concepts from a paper abstract or block of text:

```bash
python -m hivemind ingest --text "We propose a novel graph neural network that uses attention mechanisms to aggregate neighbor information." --hive gnns
```

This extracts keywords like "Graph Neural Network", "Attention Mechanisms", and ingests each one.

## Batch ingest

Create a JSON file:

```json
[
  {"keyword": "Self-Attention", "definition": "...", "hive": "transformers"},
  {"keyword": "Multi-Head Attention", "definition": "...", "hive": "transformers"}
]
```

Then ingest:

```bash
python -m hivemind ingest --batch items.json
```

## Connect to existing concepts

```bash
python -m hivemind ingest "Attention" --hive transformers --connect "Self-Attention, Multi-Head Attention"
```

## Dry run

Preview what would be added without writing:

```bash
python -m hivemind ingest "New Concept" --hive gnns --dry-run
```

## Skip resolution

To skip linking the concept to existing papers:

```bash
python -m hivemind ingest "Concept" --hive gnns --no-resolve
```
