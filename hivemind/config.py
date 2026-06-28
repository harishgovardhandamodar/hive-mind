import os
import yaml

DEFAULT_CONFIG = {
    "hives_dir": "hives",
    "meta_graph_path": "data/meta_graph.json",
    "server": {
        "host": "127.0.0.1",
        "port": 9090,
    },
}


def load(config_path: str | None = None) -> dict:
    config = DEFAULT_CONFIG.copy()

    search_paths = [
        config_path,
        "config.yaml",
        os.path.expanduser("~/.config/hivemind/config.yaml"),
    ]

    for path in search_paths:
        if path and os.path.exists(path):
            with open(path) as f:
                loaded = yaml.safe_load(f) or {}
                config.update(loaded)
            break

    root = os.path.abspath(config.get("root", "."))
    hives_dir = config["hives_dir"]
    if not os.path.isabs(hives_dir):
        config["hives_dir"] = os.path.join(root, hives_dir)

    meta_path = config["meta_graph_path"]
    if not os.path.isabs(meta_path):
        config["meta_graph_path"] = os.path.join(root, meta_path)

    os.makedirs(os.path.dirname(config["meta_graph_path"]), exist_ok=True)
    os.makedirs(config["hives_dir"], exist_ok=True)

    return config
