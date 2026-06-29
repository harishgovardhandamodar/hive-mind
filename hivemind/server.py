import json
import os
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock
from typing import Any
from urllib.parse import urlparse, unquote, parse_qs

from .config import load as load_config
from .concept_ingester import ConceptIngester, extract_keywords
from .hive_mind import HiveMind

_hm: HiveMind | None = None
_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

# SSE event bus
_sse_clients: list[BaseHTTPRequestHandler] = []
_sse_lock = Lock()
_LAST_EVENT_ID = 0


def broadcast_event(event: str, data: Any) -> None:
    global _LAST_EVENT_ID
    with _sse_lock:
        _LAST_EVENT_ID += 1
        payload = f"id: {_LAST_EVENT_ID}\nevent: {event}\ndata: {json.dumps(data)}\n\n"
        dead = []
        for client in _sse_clients:
            try:
                client.wfile.write(payload.encode("utf-8"))
                client.wfile.flush()
            except Exception:
                dead.append(client)
        for client in dead:
            try:
                _sse_clients.remove(client)
            except ValueError:
                pass


class Handler(BaseHTTPRequestHandler):

    def _read_body(self) -> str:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length).decode("utf-8") if length else ""

    def _bearer(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None

    def _check_auth(self, hive: str, role: str = "write") -> bool:
        if not _hm:
            return False
        key = self._bearer()
        info = _hm.auth_check(key, hive, role) if key else None
        if info:
            return True
        # No auth configured? Allow silently (backwards compat).
        if not _hm.auth.list_keys():
            return True
        return False

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/ingest":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            hive = body.get("hive")
            if hive and not self._check_auth(hive, "write"):
                return self._json(403, {"error": "forbidden: no write access to this hive"})
            ingester = ConceptIngester(_hm)
            keyword = body.get("keyword", "")
            definition = body.get("definition", "")
            force = body.get("force", False)
            dry_run = body.get("dry_run", False)
            no_resolve = body.get("no_resolve", False)
            text = body.get("text")
            connect_to = body.get("connect_to")
            if text:
                results = ingester.ingest_from_text(text, hive, force)
            elif keyword:
                result = ingester.ingest(keyword, definition, hive, force,
                                         connect_to=connect_to, dry_run=dry_run,
                                         resolve=not no_resolve)
                results = [result]
            else:
                return self._json(400, {"error": "provide 'keyword' or 'text'"})
            # Broadcast SSE event
            added = [r for r in results if r.get("status") == "added"]
            if added:
                broadcast_event("hive-update", {"hive": hive or "", "action": "ingest",
                                                "concepts": len(added)})
            self._json(200, {"results": results})
        elif path == "/api/arxiv-import":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            ingester = ConceptIngester(_hm)
            ids = body.get("ids", [])
            hive = body.get("hive")
            if hive and not self._check_auth(hive, "write"):
                return self._json(403, {"error": "forbidden: no write access to this hive"})
            max_concepts = body.get("max_concepts", 10)
            no_resolve = body.get("no_resolve", False)
            if not ids:
                return self._json(400, {"error": "provide 'ids' array"})
            result = ingester.import_from_arxiv(ids, hive, max_concepts, resolve=not no_resolve)
            broadcast_event("hive-update", {"hive": result.get("hive", hive), "action": "arxiv-import",
                                            "papers": len(result.get("papers_added", [])),
                                            "concepts": len(result.get("concepts_added", []))})
            self._json(200, result)
        else:
            self._json(404, {"error": "not found"})

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
                node = {
                    "id": n,
                    "label": d.get("label", n)[:60],
                    "type": d.get("type", "unknown"),
                    "title": d.get("label", n),
                    "group": (0 if d.get("type") == "paper"
                              else 1 if d.get("type") == "concept"
                              else 2),
                }
                if d.get("type") == "paper":
                    node["arxiv_id"] = d.get("arxiv_id", "")
                    node["authors"] = (d.get("authors", "") or "")[:120]
                    node["abstract"] = (d.get("abstract", "") or "")[:300]
                elif d.get("type") == "concept":
                    node["definition"] = (d.get("definition", "") or "")[:200]
                nodes.append(node)
            for u, v, d in kg.graph.edges(data=True):
                edges.append({
                    "source": u,
                    "target": v,
                    "relation": d.get("relation", "related_to"),
                    "cross_graph": d.get("cross_graph", False),
                    "target_graph": d.get("target_graph", ""),
                })
            self._json(200, {
                "id": hive_id,
                "stats": kg.stats(),
                "nodes": nodes,
                "edges": edges,
            })
        elif path == "/api/query":
            query = parsed.query
            q = unquote(query.split("=", 1)[1]) if "=" in query else ""
            result = _hm.query_relation(q) if _hm and q else {"nodes": [], "edges": [], "explanation": ""}
            self._json(200, result)
        elif path == "/api/suggest-concepts":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            ingester = ConceptIngester(_hm)
            query = parsed.query
            keyword = unquote(query.split("=", 1)[1]) if "=" in query else ""
            if not keyword:
                return self._json(400, {"error": "provide ?keyword=..."})
            suggestions = ingester.suggest_hive(keyword)
            similar = ingester.find_similar(keyword, threshold=0.4)
            self._json(200, {"suggestions": suggestions, "similar": similar[:10]})
        elif path == "/api/extract-keywords":
            query = parsed.query
            text = unquote(query.split("=", 1)[1]) if "=" in query else ""
            if not text:
                return self._json(400, {"error": "provide ?text=..."})
            keywords = extract_keywords(text)
            self._json(200, {"keywords": keywords[:30]})
        elif path == "/api/search":
            query = parsed.query
            q = unquote(query.split("=", 1)[1]) if "=" in query else ""
            results = _hm.unified_search(q) if _hm and q else []
            self._json(200, results[:50])
        elif path == "/api/events":
            self._sse_connect()
        elif path == "/api/history":
            params = parse_qs(parsed.query)
            hives = params.get("hive", [])
            if not hives or not _hm:
                self._json(400, {"error": "provide ?hive=..."})
                return
            try:
                backups = _hm.list_backups(hives[0])
                self._json(200, backups)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/rollback":
            params = parse_qs(parsed.query)
            hives = params.get("hive", [])
            versions = params.get("version", [])
            if not hives or not versions or not _hm:
                self._json(400, {"error": "provide ?hive=...&version=..."})
                return
            try:
                msg = _hm.rollback(hives[0], versions[0])
                broadcast_event("hive-update", {"hive": hives[0], "action": "rollback", "version": versions[0]})
                self._json(200, {"message": msg})
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/export":
            params = parse_qs(parsed.query)
            hives = params.get("hive", [])
            fmt = params.get("format", ["jsonld"])[0]
            if not hives or not _hm:
                self._json(400, {"error": "provide ?hive=..."})
                return
            try:
                result = _hm.export_hive(hives[0], fmt)
                self._json(200, result)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/embed":
            params = parse_qs(parsed.query)
            hives = params.get("hive", [])
            query_text = params.get("query", [None])[0]
            if not hives or not _hm:
                self._json(400, {"error": "provide ?hive=..."})
                return
            try:
                if query_text:
                    results = _hm.vector_similar(hives[0], query_text)
                    self._json(200, {"results": results, "hive": hives[0]})
                else:
                    result = _hm.embed_hive(hives[0])
                    broadcast_event("hive-update", {"hive": hives[0], "action": "embed",
                                                    "nodes": result["embedded"]})
                    self._json(200, result)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/auth/keys":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            self._json(200, _hm.auth_list_keys())
        elif path == "/api/auth/create-key":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            name = body.get("name", "unnamed")
            result = _hm.auth_create_key(name)
            self._json(200, result)
        elif path == "/api/auth/revoke":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            key_id = body.get("key_id", "")
            if _hm.auth_revoke_key(key_id):
                self._json(200, {"status": "ok", "message": f"Revoked key '{key_id}'"})
            else:
                self._json(404, {"error": f"Key '{key_id}' not found"})
        elif path == "/api/auth/grant":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            key_id = body.get("key_id", "")
            hive = body.get("hive", "")
            role = body.get("role", "read")
            if _hm.auth_grant(key_id, hive, role):
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"error": f"Key '{key_id}' not found"})
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

    def _sse_connect(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        with _sse_lock:
            _sse_clients.append(self)

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
