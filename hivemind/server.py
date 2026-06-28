import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
from urllib.parse import urlparse

from .config import load as load_config
from .hive_mind import HiveMind

_hm: HiveMind | None = None
_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("", "/index.html"):
            self._static(os.path.join(_WEB_DIR, "index.html"), "text/html")
        elif path == "/api/stats":
            self._json(200, _hm.stats() if _hm else {})
        elif path == "/api/hives":
            self._json(200, _hm.list_hives() if _hm else [])
        elif path == "/api/meta-graph":
            self._json(200, _hm.meta_graph() if _hm else {"nodes": [], "edges": []})
        elif path.startswith("/api/hive/"):
            hive_id = path.split("/")[-1]
            kg = _hm.get_hive_graph(hive_id) if _hm else None
            if not kg:
                self._json(404, {"error": f"Hive '{hive_id}' not found"})
                return
            nodes = []
            edges = []
            for n, d in kg.graph.nodes(data=True):
                nodes.append({
                    "id": n,
                    "label": d.get("label", n)[:60],
                    "type": d.get("type", "unknown"),
                    "title": d.get("label", n),
                    "group": (0 if d.get("type") == "paper"
                              else 1 if d.get("type") == "concept"
                              else 2),
                })
            for u, v, d in kg.graph.edges(data=True):
                edges.append({
                    "source": u,
                    "target": v,
                    "relation": d.get("relation", "related_to"),
                })
            self._json(200, {
                "id": hive_id,
                "stats": kg.stats(),
                "nodes": nodes,
                "edges": edges,
            })
        elif path == "/api/search":
            query = parsed.query
            q = query.split("=", 1)[1] if "=" in query else ""
            results = _hm.unified_search(q) if _hm and q else []
            self._json(200, results[:50])
        else:
            self._serve_static(path)

    def _serve_static(self, path: str) -> None:
        filepath = os.path.normpath(os.path.join(_WEB_DIR, path.lstrip("/")))
        if not filepath.startswith(os.path.normpath(_WEB_DIR)):
            return self._json(403, {"error": "forbidden"})
        if os.path.isfile(filepath):
            ext = os.path.splitext(filepath)[1].lstrip(".")
            ct = {"html": "text/html", "js": "application/javascript",
                  "css": "text/css", "png": "image/png",
                  "svg": "image/svg+xml"}.get(ext, "text/plain")
            self._static(filepath, ct)
        else:
            self._json(404, {"error": "not found"})

    def _static(self, filepath: str, ct: str) -> None:
        try:
            with open(filepath, encoding="utf-8") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
        except FileNotFoundError:
            self._json(404, {"error": "not found"})

    def _json(self, status: int, data: Any) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


def serve(host: str = "127.0.0.1", port: int = 9090,
          config: dict | None = None) -> None:
    global _hm
    config = config or load_config()
    _hm = HiveMind(config)

    server = HTTPServer((host, port), Handler)
    print(f"HiveMind Dashboard → http://{host}:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ...")
        server.shutdown()
