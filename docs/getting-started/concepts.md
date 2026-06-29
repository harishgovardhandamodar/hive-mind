---
description: Core concepts and terminology
icon: book-open
---

# Concepts

## Hive

A **hive** is a topic-specific knowledge graph — a collection of papers, concepts, and their relationships within a domain. Each hive is stored as a JSON file (`knowledge_graph.json`) in a directory under `hives/`.

## Knowledge Graph

Each hive contains a directed multigraph with three node types:

| Node type | Description |
|---|---|
| `paper` | A research paper with arXiv ID, title, authors, abstract |
| `concept` | A keyword, term, or idea extracted from papers |
| `graph_ref` | A reference to another hive (for cross-hive linking) |

Edges have a `relation` property from a controlled vocabulary: `related_to`, `introduces`, `references`, `extends`, `uses`, `contradicts`.

## Federation

The **federation** is the collection of all hives plus the **meta-graph** that tracks hive-to-hive connections. The meta-graph enables queries that span multiple domains.

## Meta-Graph

A lightweight graph where each node is a hive and each edge is a link between hives. The federation uses the meta-graph to find paths between hives during multi-hop queries.

## Concept Resolution

When a new concept is added to a hive, HiveMind automatically scans paper titles and abstracts for mentions of that concept and creates `related_to` edges. This runs by default and can be disabled with `--no-resolve`.

## Vector Embeddings

Concepts and papers can be embedded as 384-dimensional vectors using `sentence-transformers`. These enable semantic similarity search — finding conceptually related content even when exact keywords don't match.

## SSE (Server-Sent Events)

The dashboard receives real-time updates via SSE. When data changes (ingest, import, rollback, embed), all connected browsers refresh automatically.
