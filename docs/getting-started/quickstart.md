---
description: Get started with HiveMind in 5 minutes
icon: rocket-launch
---

# Quick Start

## 1. Start the server

```bash
python -m hivemind serve
```

Open [http://127.0.0.1:9090](http://127.0.0.1:9090).

## 2. Create a hive

```bash
python -m hivemind init my-hive
```

## 3. Add concepts

```bash
python -m hivemind ingest "Graph Neural Network" --hive gnns
python -m hivemind ingest "Message Passing" --hive gnns --connect "Graph Neural Network"
```

## 4. Import papers from arXiv

```bash
python -m hivemind arxiv-import 1706.03762 --hive gnns
```

This fetches "Attention Is All You Need", creates a paper node, and extracts concepts from the title and abstract.

## 5. Search

```bash
python -m hivemind search "transformer attention"
```

## 6. Query across hives

```bash
python -m hivemind search "How is Graph Neural Networks related to Attention?"
```

The dashboard also supports natural language queries in the search bar.
