---
description: API key authentication and authorization
icon: lock
---

# Access Control

The `AccessControl` class manages API-key-based permissions.

## Permission model

- **Keys** are 64-character hex strings generated via `secrets.token_hex(24)`
- **Roles**: `read`, `write`, `admin` (ordered by increasing privilege)
- **Hives**: each key can have per-hive role assignments
- **Default**: empty hives dict = admin access to all hives

## Storage

Permissions are stored in `permissions.json` alongside the meta-graph:

```json
{
  "default": {
    "name": "default-admin",
    "key": "6d04b2f0972a62c353809c38323c777c",
    "hives": {}
  },
  "abc123": {
    "name": "alice",
    "key": "c1fb5e6550811e91cc2a831d23b97d0074e38dc7995573ec",
    "hives": {
      "transformers": "read",
      "gnns": "write"
    }
  }
}
```

## Enforcement

- Mutating endpoints (`/api/ingest`, `/api/arxiv-import`) check `Authorization: Bearer <key>` header
- Public endpoints (GET) are always accessible
- No auth required if no keys exist (backwards compatibility)

## Default key

On first server start, a default admin key is created and printed to stdout. Save this key — it won't be shown again.
