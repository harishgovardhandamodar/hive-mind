import json
import logging
import os
import re
import ssl
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Lock
from typing import Any
from urllib.parse import urlparse, unquote, parse_qs

logger = logging.getLogger(__name__)

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
        cookies = self.headers.get("Cookie", "")
        for part in cookies.split(";"):
            part = part.strip()
            if part.startswith("hm_auth="):
                return part[len("hm_auth="):]
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
            if body.get("ollama"):
                os.environ["USE_OLLAMA_DEFINITIONS"] = "true"
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
            if body.get("ollama"):
                os.environ["USE_OLLAMA_DEFINITIONS"] = "true"
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
        elif path == "/api/arxiv-search":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            if body.get("ollama"):
                os.environ["USE_OLLAMA_DEFINITIONS"] = "true"
            ingester = ConceptIngester(_hm)
            query = body.get("query", "")
            hive = body.get("hive")
            max_results = body.get("max_results", 10)
            max_concepts = body.get("max_concepts", 10)
            no_resolve = body.get("no_resolve", False)
            if not query:
                return self._json(400, {"error": "provide 'query' string"})
            result = ingester.search_arxiv(query, hive, max_results, max_concepts, resolve=not no_resolve)
            broadcast_event("hive-update", {"hive": result.get("hive", hive), "action": "arxiv-search",
                                            "papers": len(result.get("papers_added", [])),
                                            "concepts": len(result.get("concepts_added", []))})
            self._json(200, result)
        elif path == "/api/enrich-definitions":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            hive = body.get("hive")
            if hive and not self._check_auth(hive, "write"):
                return self._json(403, {"error": "forbidden: no write access to this hive"})
            os.environ["USE_OLLAMA_DEFINITIONS"] = "true"
            ingester = ConceptIngester(_hm)
            result = ingester.enrich_concept_definitions(hive, body.get("force", False))
            if result.get("updated", 0) > 0:
                broadcast_event("hive-update", {"hive": hive or "all", "action": "enrich",
                                                "updated": result["updated"]})
            self._json(200, result)
        elif path == "/api/hives":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            name = body.get("name", "").strip()
            if not name:
                return self._json(400, {"error": "provide 'name'"})
            owner = body.get("owner", "").strip()
            try:
                hive_path = _hm.create_hive(name, owner=owner)
                broadcast_event("hive-update", {"hive": name, "action": "create"})
                self._json(200, {"status": "ok", "hive": name, "path": hive_path,
                                 "owner": owner})
            except (ValueError, OSError) as e:
                self._json(409, {"error": str(e)})
        elif path == "/api/collections":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            name = body.get("name", "").strip()
            if not name:
                return self._json(400, {"error": "provide 'name'"})
            description = body.get("description", "")
            try:
                c = _hm.create_collection(name, description)
                broadcast_event("collection-update", {"action": "create", "collection": c["id"]})
                self._json(200, c)
            except ValueError as e:
                self._json(409, {"error": str(e)})
        elif path.startswith("/api/collection/") and path.endswith("/hives"):
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            parts = path.split("/")
            cid = parts[-2]
            action = body.get("action", "add")
            hive_id = body.get("hive_id", "")
            if not hive_id:
                return self._json(400, {"error": "provide 'hive_id'"})
            try:
                if action == "remove":
                    c = _hm.remove_hive_from_collection(cid, hive_id)
                else:
                    c = _hm.add_hive_to_collection(cid, hive_id)
                broadcast_event("collection-update", {"action": action, "collection": cid, "hive": hive_id})
                self._json(200, c)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path.startswith("/api/collection/"):
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            cid = path.split("/")[-1]
            action = body.get("action", "delete")
            if action == "delete":
                try:
                    _hm.delete_collection(cid)
                    broadcast_event("collection-update", {"action": "delete", "collection": cid})
                    self._json(200, {"status": "ok", "collection": cid})
                except ValueError as e:
                    self._json(404, {"error": str(e)})
            else:
                self._json(400, {"error": "unknown action"})
        elif path.startswith("/api/hive/") and path.endswith("/visibility"):
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            hive_id = unquote(path.split("/")[-2])
            visible = body.get("visible", True)
            _hm.set_hive_visibility(hive_id, visible)
            broadcast_event("hive-update", {"hive": hive_id, "action": "visibility",
                                            "visible": visible})
            self._json(200, {"status": "ok", "hive": hive_id, "visible": visible})
        elif path == "/api/hives/import":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            data = body.get("data")
            if not data:
                return self._json(400, {"error": "provide 'data' with exported hive"})
            target_name = body.get("target_name")
            merge_similar = body.get("merge_similar", True)
            try:
                report = _hm.import_hive_data(data, target_name, merge_similar)
                broadcast_event("hive-update", {"hive": report["hive_id"], "action": "import"})
                self._json(200, report)
            except ValueError as e:
                self._json(400, {"error": str(e)})
        elif path == "/api/link-concepts":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            threshold = float(body.get("threshold", 0.85))
            dry_run = body.get("dry_run", True)
            apply = body.get("apply", False)
            limit = int(body.get("limit", 100))
            relation = body.get("relation", "related_to")
            result = _hm.auto_link_concepts(
                threshold=threshold,
                dry_run=not apply if apply else dry_run,
                limit=limit,
                relation=relation,
            )
            if apply and result["linked_count"]:
                broadcast_event("hive-update", {
                    "action": "link-concepts",
                    "linked": result["linked_count"],
                })
            self._json(200, result)
        elif path == "/api/layout":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            hive = body.get("hive", "")
            positions = body.get("positions", {})
            if not hive or not isinstance(positions, dict):
                return self._json(400, {"error": "provide 'hive' and 'positions'"})
            if hive and not self._check_auth(hive, "write"):
                return self._json(403, {"error": "forbidden: no write access to this hive"})
            try:
                _hm.save_hive_layout(hive, positions)
                self._json(200, {"status": "ok", "hive": hive, "nodes": len(positions)})
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/peers":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            url = body.get("url", "").strip()
            if not url:
                return self._json(400, {"error": "provide 'url'"})
            name = body.get("name", "")
            try:
                peer = _hm.add_peer(url, name)
                self._json(200, peer)
            except Exception as e:
                self._json(400, {"error": str(e)})
        elif path == "/api/peering/name":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            name = body.get("name", "").strip()
            _hm.set_instance_name(name)
            self._json(200, {"status": "ok", "instance_name": name})
        elif path == "/api/peering/invite":
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            ttl = 600
            try:
                body = json.loads(self._read_body())
                ttl = int(body.get("ttl", 600))
            except (json.JSONDecodeError, ValueError):
                pass
            invite = _hm.create_invite(ttl)
            self._json(200, invite)
        elif path == "/api/peers/pair":
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            url = body.get("url", "").strip()
            if not url:
                return self._json(400, {"error": "provide 'url'"})
            token = body.get("token")
            try:
                result = _hm.pair_with_peer(url, token)
                self._json(200, result)
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": str(e)})
        elif path == "/api/peering/pair":
            """Called by a remote instance to register us as its peer (bidirectional)."""
            try:
                body = json.loads(self._read_body())
            except (json.JSONDecodeError, ValueError):
                return self._json(400, {"error": "invalid JSON"})
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            peer_url = body.get("peer_url", "").strip()
            peer_name = body.get("peer_name", peer_url)
            instance_id = body.get("instance_id", "")
            peer_fingerprint = body.get("fingerprint", "")
            token = body.get("token")
            if not peer_url:
                return self._json(400, {"error": "provide 'peer_url'"})
            try:
                peer = _hm.accept_pair(peer_url, peer_name, instance_id,
                                       peer_fingerprint, token)
                self._json(200, {"status": "ok", "peer": peer})
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                self._json(400, {"error": str(e)})
        elif path.startswith("/api/peers/") and path.endswith("/sync"):
            pid = path.split("/")[-2]
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            try:
                reports = _hm.pull_peer_hives(pid)
                self._json(200, {"peer_id": pid, "results": reports})
            except ValueError as e:
                self._json(404, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": str(e)})
        elif re.match(r"^/api/peers/[^/]+/pull/.+$", path):
            parts = path.split("/")
            pid = parts[-3]
            hive_id = unquote(parts[-1])
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            try:
                reports = _hm.pull_peer_hives(pid, hive_id)
                self._json(200, {"peer_id": pid, "hive_id": hive_id, "results": reports})
            except ValueError as e:
                self._json(404, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": str(e)})
        else:
            self._json(404, {"error": "not found"})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path.startswith("/api/peers/"):
            pid = path.split("/")[-1]
            if not _hm:
                return self._json(503, {"error": "not ready"})
            try:
                _hm.remove_peer(pid)
                self._json(200, {"status": "ok", "peer": pid})
            except ValueError as e:
                self._json(404, {"error": str(e)})
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
        elif re.match(r"^/api/hive/.+/export-data$", path):
            hive_id = unquote(path.split("/")[-2])
            if not _hm:
                return self._json(503, {"error": "server not ready"})
            try:
                result = _hm.export_hive_data(hive_id)
                self._json(200, result)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path.startswith("/api/hive/"):
            hive_id = unquote(path.split("/")[-1])
            kg = _hm.get_hive_graph(hive_id) if _hm else None
            if not kg:
                self._json(404, {"error": f"Hive '{hive_id}' not found"})
                return
            layout = kg.load_layout()
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
                pos = layout.get(n)
                if pos:
                    node["layout_x"] = pos.get("x")
                    node["layout_y"] = pos.get("y")
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
        elif path == "/api/compare":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            params = parse_qs(parsed.query)
            hives_raw = params.get("hives", [None])[0]
            if not hives_raw:
                self._json(400, {"error": "provide ?hives=hive1,hive2,..."})
                return
            hive_ids = [unquote(h.strip()) for h in hives_raw.split(",") if h.strip()]
            if len(hive_ids) < 2:
                self._json(400, {"error": "provide at least 2 hive IDs"})
                return
            try:
                result = _hm.compare_hives(hive_ids)
                self._json(200, result)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/collections":
            self._json(200, _hm.list_collections() if _hm else [])
        elif path == "/api/collection":
            params = parse_qs(parsed.query)
            cid = params.get("id", [None])[0]
            if not cid:
                self._json(400, {"error": "provide ?id=..."})
                return
            try:
                self._json(200, _hm.get_collection(cid))
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path.startswith("/api/collection/"):
            cid = path.split("/")[-1]
            try:
                self._json(200, _hm.get_collection(cid))
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/search":
            query = parsed.query
            q = unquote(query.split("=", 1)[1]) if "=" in query else ""
            results = _hm.unified_search(q) if _hm and q else []
            self._json(200, {"total": len(results), "results": results[:50]})
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
            metric = params.get("metric", ["cosine"])[0]
            if not hives or not _hm:
                self._json(400, {"error": "provide ?hive=..."})
                return
            try:
                if query_text:
                    results = _hm.vector_similar(hives[0], query_text, metric=metric)
                    self._json(200, {"results": results, "hive": hives[0], "metric": metric})
                else:
                    result = _hm.embed_hive(hives[0])
                    broadcast_event("hive-update", {"hive": hives[0], "action": "embed",
                                                    "nodes": result["embedded"]})
                    self._json(200, result)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/peering/info":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            info = _hm.instance_info()
            info["host"] = self.headers.get("Host", "unknown")
            self._json(200, info)
        elif path == "/api/peering/hives":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            hives = [{"id": h["id"], "papers": h["papers"],
                      "concepts": h["concepts"], "relations": h["relations"]}
                     for h in _hm.list_hives()]
            self._json(200, hives)
        elif re.match(r"^/api/peering/hive/.+$", path):
            hive_id = unquote(path.split("/")[-1])
            if not _hm:
                return self._json(503, {"error": "not ready"})
            try:
                result = _hm.export_hive_data(hive_id)
                result["_forwarded_from"] = f"{self.headers.get('Host', 'unknown')}"
                self._json(200, result)
            except ValueError as e:
                self._json(404, {"error": str(e)})
        elif path == "/api/peers":
            if not _hm:
                return self._json(503, {"error": "not ready"})
            self._json(200, _hm.list_peers())
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
            if _hm and _hm.auth.list_keys() and ct == "text/html":
                keys = _hm.auth.list_keys()
                if keys:
                    kid = keys[0]["id"]
                    key = _hm.auth._permissions.get(kid, {}).get("key", "")
                    if key:
                        self.send_header("Set-Cookie",
                            f"hm_auth={key}; Path=/; SameSite=Lax; HttpOnly")
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
        logger.info(fmt, *args)


def serve(host: str = "127.0.0.1", port: int = 9090,
          config: dict | None = None,
          certfile: str | None = None,
          keyfile: str | None = None) -> None:
    global _hm
    config = config or load_config()
    _hm = HiveMind(config)

    # Determine scheme and public URL
    use_tls = bool(certfile and keyfile)
    scheme = "https" if use_tls else "http"
    public_url = os.environ.get("HIVEMIND_PUBLIC_URL", f"{scheme}://{host}:{port}")
    _hm.set_public_url(public_url)

    server = ThreadingHTTPServer((host, port), Handler)

    if use_tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        logger.info("TLS enabled (cert=%s)", certfile)

    logger.info("HiveMind Dashboard → %s://%s:%s", scheme, host, port)
    logger.info("Public URL → %s", public_url)
    logger.info("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down ...")
        server.shutdown()
