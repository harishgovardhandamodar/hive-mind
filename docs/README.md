---
description: Federated knowledge graphs for research intelligence
icon: hive
---

# HiveMind

HiveMind is a federated knowledge graph platform that lets you build, connect, and query topic-specific knowledge graphs called **hives**. Each hive indexes papers, concepts, and their relationships within a domain. Hives are linked through a meta-graph, enabling cross-domain queries and serendipitous discovery.

{% hint style="info" %}
HiveMind runs as a single binary — start it with `python -m hivemind serve` and open `http://127.0.0.1:9090` in your browser.
{% endhint %}

## Key Features

{% columns %}
{% column %}
### 📚 Paper Management
Import papers from arXiv, extract concepts automatically, and link them to relevant papers.
{% endcolumn %}

{% column %}
### 🔗 Federation
Connect hives through a meta-graph. Query across domains without knowing the topology.
{% endcolumn %}
{% endcolumns %}

{% columns %}
{% column %}
### 🧠 Vector Search
Semantic embeddings with `sentence-transformers` for finding conceptually similar content.
{% endcolumn %}

{% column %}
### 🔐 Access Control
API-key-based permissions with read/write/admin roles per hive.
{% endcolumn %}
{% endcolumns %}

## Quick Start

```bash
pip install -r requirements.txt
python -m hivemind serve
```

Open [http://127.0.0.1:9090](http://127.0.0.1:9090) to see the dashboard.

## Next Steps

<table data-view="cards">
  <thead>
    <tr>
      <th>Guide</th>
      <th data-card-target data-type="content-ref">Link</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Installation</td>
      <td><a href="getting-started/installation.md">Installation Guide</a></td>
    </tr>
    <tr>
      <td>Quick Start</td>
      <td><a href="getting-started/quickstart.md">Get started in 5 minutes</a></td>
    </tr>
    <tr>
      <td>CLI Reference</td>
      <td><a href="cli/commands.md">All Commands</a></td>
    </tr>
    <tr>
      <td>API Reference</td>
      <td><a href="api/endpoints.md">REST API</a></td>
    </tr>
  </tbody>
</table>
