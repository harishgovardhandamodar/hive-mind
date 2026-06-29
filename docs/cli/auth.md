---
description: Managing API keys and permissions
icon: lock
---

# Auth

## Create a key

```bash
python -m hivemind auth create-key alice
```

Output:

```
Created key 'alice':
  ID:  abc123def456
  Key: <64-character-hex-secret>
  Store this key safely — it will not be shown again.
```

## List keys

```bash
python -m hivemind auth list
```

## Grant hive access

```bash
python -m hivemind auth grant abc123def456 transformers --role write
```

Roles: `read`, `write`, `admin`.

## Revoke a key

```bash
python -m hivemind auth revoke abc123def456
```

## Revoke hive access

```bash
# Via API only — POST /api/auth/revoke with body {"key_id": "abc123", "hive": "transformers"}
```

## Default admin key

When no permissions file exists, HiveMind creates a default admin key on first run. This key has access to all hives (empty hives dict = admin everywhere).

## Using keys with the API

```bash
curl -H "Authorization: Bearer <key>" http://127.0.0.1:9090/api/ingest \
  -d '{"keyword": "New Concept", "hive": "transformers"}'
```

## Backwards compatibility

If no API keys exist, mutating endpoints are accessible without authentication. As soon as the first key is created, auth is enforced.
