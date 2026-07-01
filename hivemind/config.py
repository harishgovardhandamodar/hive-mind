import os
import yaml

DEFAULT_CONFIG = {
    "hives_dir": "hives",
    "meta_graph_path": "data/meta_graph.json",
    "vector_store": {
        # sentence-transformers model config for VectorStore instantiation
        "model_name": "all-MiniLM-L6-v2",
        # similarity metric to use: cosine, euclidean, manhattan, dot
        "similarity_metric": "cosine",
        # max LRU cache entries per VectorStore instance
        "cache_size": 128,
        # default vector similarity threshold for search
        "threshold_vector": 0.5,
        # default fuzzy match threshold as fallback
        "threshold_fuzzy": 0.3,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 9090,
    },
}


def load(config_path=None):
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
