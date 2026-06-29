---
description: Configuration file reference
icon: gear
---

# Configuration

## config.yaml

```yaml
hives_dir: hives
meta_graph_path: data/meta_graph.json
server:
  host: 127.0.0.1
  port: 9090
```

| Field | Default | Description |
|---|---|---|
| `hives_dir` | `hives` | Directory containing hive subdirectories |
| `meta_graph_path` | `data/meta_graph.json` | Path to the federation meta-graph |
| `server.host` | `127.0.0.1` | Server bind address |
| `server.port` | `9090` | Server port |

## Config resolution

`config.py` searches for a configuration file in this order:

1. `./config.yaml` (current working directory)
2. `~/.config/hivemind/config.yaml`
3. Falls back to defaults

Relative paths in the config are resolved against the directory containing the config file.

## Environment variables

Not currently supported. Use `config.yaml` for all configuration.
