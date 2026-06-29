---
description: Install HiveMind on your machine
icon: download
---

# Installation

## Prerequisites

- Python 3.10+
- pip

## Install from source

```bash
git clone <repository-url>
cd hive-mind
pip install -r requirements.txt
```

## Optional dependencies

For vector embeddings with semantic search:

```bash
pip install sentence-transformers
```

This enables the `all-MiniLM-L6-v2` model (384-dimensional embeddings) for concept similarity.

## Verify installation

```bash
python -m hivemind stats
```

You should see federation statistics showing 0 graphs.

## Docker

```bash
docker compose up -d
```

This builds the image, starts the server on port 9090, and mounts `./hives` and `./data` as volumes for persistence.

{% hint style="info" %}
The Dockerfile uses `python:3.12-slim`. To include sentence-transformers, add it to `requirements.txt` before building.
{% endhint %}
