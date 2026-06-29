---
description: All CLI commands
icon: terminal
---

# Commands

## Usage

```bash
python -m hivemind <command> [options]
```

## Command list

| Command | Description |
|---|---|
| `init <name>` | Create a new hive |
| `list` | List all hives |
| `inspect <name>` | Show detailed hive info |
| `link <source> <target>` | Link two hives in the meta-graph |
| `connect <src> <cA> <tgt> <cB>` | Cross-hive concept connection |
| `search <query>` | Unified search across all hives |
| `ingest <keyword>` | Add a concept to a hive |
| `arxiv-import <ids...>` | Import papers from arXiv |
| `import <path>` | Import an arxiv-to-obsidian project |
| `suggest <keyword>` | Suggest hives for a keyword |
| `export <name>` | Export a hive (JSON-LD or Obsidian) |
| `embed <name>` | Generate vector embeddings |
| `history <name>` | Show backup versions |
| `diff <name> <version>` | Diff against a backup |
| `rollback <name> <version>` | Restore a backup |
| `auth <subcommand>` | Manage API keys and permissions |
| `serve` | Start web dashboard |
| `stats` | Federation statistics |

## Global flags

- `--help` or `-h` — Show help for any command
