---
description: Authenticating with the API
icon: key
---

# Authentication

## Bearer token

Mutating endpoints require authentication when at least one API key exists. Include the key in the `Authorization` header:

```bash
curl -H "Authorization: Bearer <your-api-key>" \
  http://127.0.0.1:9090/api/ingest \
  -d '{"keyword": "New Concept", "hive": "transformers"}'
```

## Creating keys

```bash
python -m hivemind auth create-key alice
```

## Granting access

```bash
python -m hivemind auth grant <key-id> transformers --role write
```

Roles:

| Role | Access |
|---|---|
| `read` | View hives, search, query |
| `write` | Ingest concepts, import papers, edit |
| `admin` | Full access, including auth management |

## Default admin key

On first run, HiveMind creates a default admin key printed to stdout. This key has access to all hives.

## Backwards compatibility

No auth is required if no API keys exist. The first `auth create-key` invocation creates a permissions file and enables enforcement.
