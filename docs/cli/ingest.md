---
description: The ingest command in detail
icon: plus-circle
---

# Ingest

```bash
python -m hivemind ingest [keyword] [options]
```

## Options

| Flag | Description |
|---|---|
| `--hive`, `-H` | Target hive (auto-suggested if omitted) |
| `--definition`, `-d` | Definition text for the concept |
| `--text`, `-t` | Extract keywords from text and ingest each |
| `--batch`, `-b` | Path to JSON file with batch items |
| `--connect`, `-c` | Connect to existing concepts (comma-separated) |
| `--force`, `-f` | Add even if similar concept exists |
| `--dry-run`, `-n` | Preview without writing |
| `--no-resolve` | Skip linking concept to existing papers |
| `--suggest` | Only suggest a hive, don't add |

## Examples

```bash
# Basic ingest
python -m hivemind ingest "Graph Neural Network" --hive gnns

# Ingest with definition
python -m hivemind ingest "Transformer" -d "Attention-based architecture" -H transformers

# Extract from text
python -m hivemind ingest --text "We propose a novel architecture..." --hive gnns

# Batch ingest
python -m hivemind ingest --batch concepts.json

# Connect to existing concepts
python -m hivemind ingest "Attention" --hive transformers -c "Self-Attention,Multi-Head Attention"

# Preview only
python -m hivemind ingest "New Concept" --dry-run

# Skip concept-to-paper linking
python -m hivemind ingest "Concept" --no-resolve
```
