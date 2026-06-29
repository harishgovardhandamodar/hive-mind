---
description: Exporting hives in various formats
icon: file-export
---

# Exporting

## JSON-LD

Export a hive as JSON-LD for interoperability with semantic web tools:

```bash
python -m hivemind export transformers --format jsonld > transformers.jsonld
```

The output uses the `@context` + `@graph` structure with typed nodes and edges:

```json
{
  "@context": {
    "hivemind": "https://hivemind.local/ns/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
  },
  "@graph": [
    {
      "@id": "hivemind:transformers:paper:1706.03762",
      "@type": "hivemind:paper",
      "label": "Attention Is All You Need",
      "arxiv_id": "1706.03762",
      "authors": "Vaswani et al."
    }
  ]
}
```

## Obsidian

Export as Obsidian-compatible Markdown files:

```bash
python -m hivemind export transformers --format obsidian --output ./obsidian-vault
```

This creates one `.md` file per node with:

- YAML-style metadata (`type::`, `graph_id::`, `authors::`)
- Abstract, definition, and arXiv link
- `## Connections` section with `[[wikilinks]]` to related nodes

## API

```bash
curl "http://127.0.0.1:9090/api/export?hive=transformers&format=jsonld"
```
