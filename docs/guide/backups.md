---
description: Backup, diff, and rollback hives
icon: clock-rotate-left
---

# Backups & Rollback

Every time a knowledge graph is saved, the previous version is automatically backed up with a timestamp.

## View backup history

```bash
python -m hivemind history transformers
```

Output:

```
Backup history for 'transformers':
Version                  Papers   Concepts       Size
----------------------------------------------------
20260628_231948              19         27     22950
```

## Diff against a backup

```bash
python -m hivemind diff transformers 20260628_231948
```

Shows added and removed nodes between the current state and the backup.

## Rollback

```bash
python -m hivemind rollback transformers 20260628_231948
```

This restores the hive to the backup version. The current state is saved as a new backup before the rollback, so you can undo the rollback too.

## Backup storage

Backups are stored in `hives/<name>/data/graph/backups/YYYYMMDD_HHMMSS.json`. They are excluded from version control via `.gitignore`.

## API

```bash
# List backups
curl "http://127.0.0.1:9090/api/history?hive=transformers"

# Rollback
curl "http://127.0.0.1:9090/api/rollback?hive=transformers&version=20260628_231948"
```
