import argparse
import logging
import sys

import json

from .config import load as load_config
from .concept_ingester import ConceptIngester, extract_keywords
from .hive_mind import HiveMind


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="hivemind – federated knowledge graphs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  hivemind init my-hive\n"
            "  hivemind list\n"
            "  hivemind link source-hive target-hive\n"
            "  hivemind connect src-hive concept:A tgt-hive concept:B --relation extends\n"
            "  hivemind search 'transformer attention'\n"
            "  hivemind import /path/to/graph --name my-hive\n"
            "  hivemind history my-hive\n"
            "  hivemind diff my-hive 20250628_120000\n"
            "  hivemind rollback my-hive 20250628_120000\n"
            "  hivemind embed my-hive\n"
            "  hivemind embed my-hive --query 'graph neural network'\n"
            "  hivemind export my-hive --format jsonld\n"
            "  hivemind export my-hive --format obsidian --output ./obsidian-vault\n"
            "  hivemind auth create-key alice\n"
            "  hivemind auth grant <key-id> my-hive --role write\n"
            "  hivemind auth list\n"
            "  hivemind serve\n"
            "  hivemind stats\n"
        ),
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Create a new hive (knowledge graph)")
    p_init.add_argument("name", help="Hive name")

    sub.add_parser("list", help="List all hives")

    p_link = sub.add_parser("link", help="Link two hives with a reference")
    p_link.add_argument("source", help="Source hive name")
    p_link.add_argument("target", help="Target hive name")
    p_link.add_argument("--relation", "-r", default="references",
                        help="Relation type (default: references)")

    p_connect = sub.add_parser("connect",
                                help="Connect concepts across different hives")
    p_connect.add_argument("source_graph", help="Source hive name")
    p_connect.add_argument("concept_a", help="Concept in source hive")
    p_connect.add_argument("target_graph", help="Target hive name")
    p_connect.add_argument("concept_b", help="Concept in target hive")
    p_connect.add_argument("--relation", "-r", default="related_to",
                           help="Relation type (default: related_to)")

    p_search = sub.add_parser("search", help="Unified search across all hives")
    p_search.add_argument("query", help="Search query")

    p_arxiv = sub.add_parser("arxiv-import",
                              help="Import papers from arxiv by IDs into a hive")
    p_arxiv.add_argument("ids", nargs="+", help="Arxiv paper IDs (e.g. 1706.03762)")
    p_arxiv.add_argument("--hive", "-H", help="Target hive (auto-created if omitted)")
    p_arxiv.add_argument("--max-concepts", "-m", type=int, default=10,
                         help="Max concepts to extract per paper")
    p_arxiv.add_argument("--no-resolve", action="store_true",
                         help="Skip linking concepts to existing papers")

    p_import = sub.add_parser("import",
                               help="Import an arxiv-to-obsidian knowledge graph")
    p_import.add_argument("path", help="Path to arxiv-to-obsidian project directory")
    p_import.add_argument("--name", "-n", help="Hive name (default: dir basename)")

    p_serve = sub.add_parser("serve", help="Start web dashboard")
    p_serve.add_argument("--port", "-p", type=int, default=9090,
                         help="Port (default 9090)")
    p_serve.add_argument("--host", type=str, default="127.0.0.1",
                         help="Host (default 127.0.0.1)")

    p_ingest = sub.add_parser("ingest", help="Ingest new concepts/keywords into a hive")
    p_ingest.add_argument("keyword", nargs="?", help="Concept name to add")
    p_ingest.add_argument("--hive", "-H", help="Target hive (auto-suggested if omitted)")
    p_ingest.add_argument("--definition", "-d", default="", help="Definition text")
    p_ingest.add_argument("--text", "-t", help="Extract keywords from text and ingest")
    p_ingest.add_argument("--connect", "-c", nargs="*",
                          help="Connect to existing concepts in the target hive")
    p_ingest.add_argument("--force", "-f", action="store_true",
                          help="Add even if similar concept exists")
    p_ingest.add_argument("--no-resolve", action="store_true",
                          help="Skip linking concept to matching papers")
    p_ingest.add_argument("--dry-run", "-n", action="store_true",
                          help="Preview what would be added without writing")
    p_ingest.add_argument("--suggest", action="store_true",
                          help="Only suggest, don't add")
    p_ingest.add_argument("--batch", "-b", help="Path to JSON file with batch items")

    p_suggest = sub.add_parser("suggest", help="Suggest hives for a keyword")
    p_suggest.add_argument("keyword", help="Keyword to find matching hives for")

    p_inspect = sub.add_parser("inspect", help="Show detailed info about a hive")
    p_inspect.add_argument("name", help="Hive name")

    p_history = sub.add_parser("history", help="Show backup history for a hive")
    p_history.add_argument("name", help="Hive name")

    p_diff = sub.add_parser("diff", help="Show changed nodes/edges between current state and a backup")
    p_diff.add_argument("name", help="Hive name")
    p_diff.add_argument("version", help="Backup version to diff against")

    p_rollback = sub.add_parser("rollback", help="Restore a hive to a previous backup version")
    p_rollback.add_argument("name", help="Hive name")
    p_rollback.add_argument("version", help="Backup version to restore")

    p_export = sub.add_parser("export", help="Export a hive in a specific format")
    p_export.add_argument("name", help="Hive name")
    p_export.add_argument("--format", "-f", default="jsonld",
                         choices=["jsonld", "obsidian"],
                         help="Export format (default: jsonld)")
    p_export.add_argument("--output", "-o", default="",
                         help="Output directory (for obsidian format)")

    p_embed = sub.add_parser("embed", help="Generate vector embeddings for a hive")
    p_embed.add_argument("name", help="Hive name")
    p_embed.add_argument("--query", "-q", help="Search similar concepts by text (requires existing embeddings)")

    p_auth = sub.add_parser("auth", help="Manage API keys and permissions")
    p_auth_sub = p_auth.add_subparsers(dest="auth_command")
    p_auth_create = p_auth_sub.add_parser("create-key", help="Create a new API key")
    p_auth_create.add_argument("name", help="Human-readable name for the key")
    p_auth_list = p_auth_sub.add_parser("list", help="List all API keys")
    p_auth_revoke = p_auth_sub.add_parser("revoke", help="Revoke an API key")
    p_auth_revoke.add_argument("key_id", help="Key ID to revoke")
    p_auth_grant = p_auth_sub.add_parser("grant", help="Grant hive access to a key")
    p_auth_grant.add_argument("key_id", help="Key ID")
    p_auth_grant.add_argument("hive", help="Hive name")
    p_auth_grant.add_argument("--role", "-r", default="read", choices=["read", "write", "admin"],
                              help="Access role (default: read)")

    p_coll = sub.add_parser("collections", help="Manage hive collections")
    p_coll_sub = p_coll.add_subparsers(dest="coll_command")
    p_coll_create = p_coll_sub.add_parser("create", help="Create a new collection")
    p_coll_create.add_argument("name", help="Collection name")
    p_coll_create.add_argument("--description", "-d", default="", help="Description")
    p_coll_list = p_coll_sub.add_parser("list", help="List all collections")
    p_coll_get = p_coll_sub.add_parser("get", help="Show collection details")
    p_coll_get.add_argument("id", help="Collection ID")
    p_coll_delete = p_coll_sub.add_parser("delete", help="Delete a collection")
    p_coll_delete.add_argument("id", help="Collection ID")
    p_coll_add = p_coll_sub.add_parser("add", help="Add a hive to a collection")
    p_coll_add.add_argument("id", help="Collection ID")
    p_coll_add.add_argument("hive_id", help="Hive ID")
    p_coll_remove = p_coll_sub.add_parser("remove", help="Remove a hive from a collection")
    p_coll_remove.add_argument("id", help="Collection ID")
    p_coll_remove.add_argument("hive_id", help="Hive ID")

    sub.add_parser("stats", help="Show federation statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    config = load_config()
    hm = HiveMind(config)

    if args.command == "init":
        path = hm.create_hive(args.name)
        print(f"Created hive at {path}")

    elif args.command == "list":
        hives = hm.list_hives()
        if not hives:
            print("No hives found.")
            return
        print(f"{'Hive':<24} {'Papers':>8} {'Concepts':>10} {'Refs':>6} "
              f"{'Edges':>8}")
        print("-" * 60)
        for h in hives:
            refs = h.get("graph_refs", 0)
            print(f"{h['id']:<24} {h['papers']:>8} {h['concepts']:>10} "
                  f"{refs:>6} {h['relations']:>8}")

    elif args.command == "link":
        hm.link_hives(args.source, args.target, args.relation)
        print(f"Linked '{args.source}' -> '{args.target}' ({args.relation})")

    elif args.command == "connect":
        hm.connect_concepts(args.source_graph, args.concept_a,
                            args.target_graph, args.concept_b,
                            args.relation)
        print(f"Connected {args.source_graph}:{args.concept_a} "
              f"-{args.relation}-> {args.target_graph}:{args.concept_b}")

    elif args.command == "search":
        results = hm.unified_search(args.query)
        if not results:
            print("No matches found.")
            return
        print(f"{'Graph':<20} {'Node':<40} {'Type':<12} {'Label'}")
        print("-" * 100)
        for r in results[:30]:
            print(f"{r['graph_id']:<20} {r['node_id']:<40} "
                  f"{r['type']:<12} {r['label'][:50]}")

    elif args.command == "import":
        gid = hm.import_from_arxiv_to_obsidian(args.path, args.name)
        print(f"Imported as hive '{gid}'")

    elif args.command == "serve":
        from .server import serve as run_server
        run_server(host=args.host, port=args.port, config=config)

    elif args.command == "arxiv-import":
        ingester = ConceptIngester(hm)
        result = ingester.import_from_arxiv(
            args.ids, args.hive, args.max_concepts, resolve=not args.no_resolve,
        )
        print(result["message"])
        if result.get("papers_added"):
            print(f"  Papers: {len(result['papers_added'])}")
        if result.get("concepts_added"):
            print(f"  Concepts: {len(result['concepts_added'])}")

    elif args.command == "inspect":
        kg = hm.get_hive_graph(args.name)
        if not kg:
            print(f"Hive '{args.name}' not found.")
            sys.exit(1)
        s = kg.stats()
        gid = kg.graph_id
        print(f"Hive: {gid}")
        print(f"  Path:   {kg.path}")
        print(f"  Papers: {s['papers']}")
        print(f"  Concepts: {s['concepts']}")
        print(f"  Graph refs: {s['graph_refs']}")
        print(f"  Relations: {s['relations']}")
        print(f"  Cross-graph edges: {s['cross_edges']}")
        refs = kg.get_all_graph_refs()
        if refs:
            print("  References to:")
            for r in refs:
                print(f"    - {r['target_graph_id']} ({r['label']})")
        cross = kg.get_cross_edges()
        if cross:
            print("  Cross-graph edges:")
            for e in cross:
                print(f"    {e['source']} --{e['relation']}--> {e['target']}")

    elif args.command == "ingest":
        ingester = ConceptIngester(hm)
        if args.suggest and args.keyword:
            suggestions = ingester.suggest_hive(args.keyword)
            if not suggestions:
                print(f"No hives found for '{args.keyword}'.")
            else:
                print(f"Suggested hives for '{args.keyword}':")
                for s in suggestions:
                    tag = " (exists)" if s["existing_concept"] else ""
                    print(f"  {s['graph_id']:<24} score={s['score']:.2f}{tag}")
            return
        if args.text:
            results = ingester.ingest_from_text(args.text, args.hive, args.force)
        elif args.batch:
            with open(args.batch) as f:
                items = json.load(f)
            results = ingester.ingest_batch(items, args.hive, args.force)
        elif args.keyword:
            results = [ingester.ingest(args.keyword, args.definition,
                                        args.hive, args.force,
                                        connect_to=args.connect,
                                        dry_run=args.dry_run,
                                        resolve=not args.no_resolve)]
        else:
            print("Provide a keyword, --text, or --batch. Use --suggest to preview.")
            return
        for r in results:
            status = r["status"]
            icon = {"added": "✓", "skipped": "~", "error": "✗", "dry_run": "?"}.get(status, "?")
            print(f"{icon}  {r['message']}")
            if r.get("similar"):
                print(f"    Similar: {', '.join(s['label'] for s in r['similar'])}")

    elif args.command == "suggest":
        ingester = ConceptIngester(hm)
        suggestions = ingester.suggest_hive(args.keyword)
        if not suggestions:
            print(f"No hives found for '{args.keyword}'.")
            return
        print(f"Hive suggestions for '{args.keyword}':")
        for s in suggestions:
            tag = " (exists)" if s["existing_concept"] else ""
            print(f"  {s['graph_id']:<24} score={s['score']:.2f}{tag}")

    elif args.command == "history":
        try:
            backups = hm.list_backups(args.name)
        except ValueError as e:
            print(e)
            sys.exit(1)
        if not backups:
            print(f"No backups for hive '{args.name}'.")
            return
        print(f"Backup history for '{args.name}':")
        print(f"{'Version':<22} {'Papers':>8} {'Concepts':>10} {'Size':>10}")
        print("-" * 52)
        for b in backups:
            print(f"{b['timestamp']:<22} {b['papers']:>8} {b['concepts']:>10} {b['size']:>10}")

    elif args.command == "diff":
        try:
            current_data = hm.get_hive_graph(args.name)
            if not current_data:
                print(f"Hive '{args.name}' not found.")
                sys.exit(1)
            backup_data = hm.get_backup(args.name, args.version)
            if not backup_data:
                print(f"Backup '{args.version}' not found for hive '{args.name}'.")
                sys.exit(1)
        except ValueError as e:
            print(e)
            sys.exit(1)
        current_nodes = {(n, d.get("label", n), d.get("type", ""))
                         for n, d in current_data.graph.nodes(data=True)}
        curr_labels = {n for n, _, _ in current_nodes}
        backup_nodes = {(n["id"], n.get("label", n["id"]), n.get("type", ""))
                        for n in backup_data.get("nodes", [])}
        back_labels = {n for n, _, _ in backup_nodes}
        added = curr_labels - back_labels
        removed = back_labels - curr_labels
        if not added and not removed:
            print("No changes — current state matches backup.")
        else:
            if added:
                print("Added nodes:")
                for n in sorted(added):
                    print(f"  + {n}")
            if removed:
                print("Removed nodes:")
                for n in sorted(removed):
                    print(f"  - {n}")

    elif args.command == "rollback":
        try:
            msg = hm.rollback(args.name, args.version)
            print(msg)
        except ValueError as e:
            print(e)
            sys.exit(1)

    elif args.command == "export":
        try:
            result = hm.export_hive(args.name, args.format, args.output or None)
            if args.format == "jsonld":
                print(json.dumps(result, indent=2))
            elif args.format == "obsidian":
                if args.output:
                    print(f"Exported {len(result)} markdown files to {args.output}")
                else:
                    for fname, content in result.items():
                        print(f"--- {fname}.md ---")
                        print(content)
                        print()
        except ValueError as e:
            print(e)
            sys.exit(1)

    elif args.command == "embed":
        try:
            if args.query:
                results = hm.vector_similar(args.name, args.query)
                if not results:
                    print(f"No vectors found for hive '{args.name}'. Run 'hivemind embed {args.name}' first.")
                else:
                    print(f"Top matches for '{args.query}' in hive '{args.name}':")
                    print(f"{'Node':<36} {'Type':<12} {'Similarity':>10}")
                    print("-" * 60)
                    for r in results:
                        print(f"{r['node_id']:<36} {r['type']:<12} {r['similarity']:>10.4f}")
            else:
                vs = hm.get_vector_store(args.name)
                if vs and vs.has_vectors():
                    print(f"Re-embedding '{args.name}' (existing {vs.stats()['nodes']} vectors)...")
                result = hm.embed_hive(args.name)
                print(f"Embedded {result['embedded']} nodes in hive '{result['hive']}'")
                print(f"  Backend: {result['stats']['backends']}")
                print(f"  Dims:    {result['stats']['dims']}")
        except ValueError as e:
            print(e)
            sys.exit(1)

    elif args.command == "auth":
        if args.auth_command == "create-key":
            result = hm.auth_create_key(args.name)
            print(f"Created key '{result['name']}':")
            print(f"  ID:  {result['id']}")
            print(f"  Key: {result['key']}")
            print("  Store this key safely — it will not be shown again.")
        elif args.auth_command == "list":
            keys = hm.auth_list_keys()
            if not keys:
                print("No API keys.")
            else:
                print(f"{'ID':<20} {'Name':<24} {'Hives':<30}")
                print("-" * 76)
                for k in keys:
                    hives = ", ".join(f"{h}({r})" for h, r in k.get("hives", {}).items())
                    print(f"{k['id']:<20} {k['name']:<24} {hives:<30}")
        elif args.auth_command == "revoke":
            if hm.auth_revoke_key(args.key_id):
                print(f"Revoked key '{args.key_id}'")
            else:
                print(f"Key '{args.key_id}' not found")
                sys.exit(1)
        elif args.auth_command == "grant":
            if hm.auth_grant(args.key_id, args.hive, args.role):
                print(f"Granted '{args.role}' access to hive '{args.hive}' for key '{args.key_id}'")
            else:
                print(f"Key '{args.key_id}' not found")
                sys.exit(1)
        else:
            print("Usage: hivemind auth <create-key|list|revoke|grant> ...")

    elif args.command == "collections":
        if args.coll_command == "create":
            c = hm.create_collection(args.name, args.description)
            print(f"Created collection '{c['name']}' (id: {c['id']})")
        elif args.coll_command == "list":
            cols = hm.list_collections()
            if not cols:
                print("No collections.")
                return
            print(f"{'ID':<24} {'Name':<24} {'Hives':>6} {'Created'}")
            print("-" * 70)
            for c in cols:
                print(f"{c['id']:<24} {c['name']:<24} {c['hive_count']:>6} {c['created_at']}")
        elif args.coll_command == "get":
            try:
                c = hm.get_collection(args.id)
                print(f"Collection: {c['name']} ({c['id']})")
                print(f"  Description: {c['description'] or '(none)'}")
                print(f"  Created: {c['created_at']}")
                print(f"  Updated: {c['updated_at']}")
                print(f"  Hives ({len(c['hives'])}):")
                for h in c['hives']:
                    print(f"    - {h['id']} ({h['papers']} papers, {h['concepts']} concepts)")
            except ValueError as e:
                print(e)
                sys.exit(1)
        elif args.coll_command == "delete":
            try:
                hm.delete_collection(args.id)
                print(f"Deleted collection '{args.id}'")
            except ValueError as e:
                print(e)
                sys.exit(1)
        elif args.coll_command == "add":
            try:
                hm.add_hive_to_collection(args.id, args.hive_id)
                print(f"Added hive '{args.hive_id}' to collection '{args.id}'")
            except ValueError as e:
                print(e)
                sys.exit(1)
        elif args.coll_command == "remove":
            try:
                hm.remove_hive_from_collection(args.id, args.hive_id)
                print(f"Removed hive '{args.hive_id}' from collection '{args.id}'")
            except ValueError as e:
                print(e)
                sys.exit(1)
        else:
            print("Usage: hivemind collections <create|list|get|delete|add|remove> ...")

    elif args.command == "stats":
        s = hm.stats()
        print("HiveMind Federation Statistics")
        print(f"  Knowledge Graphs: {s['graphs']}")
        print(f"  Papers:           {s['papers']}")
        print(f"  Concepts:         {s['concepts']}")
        print(f"  Relations:        {s['relations']}")
        print(f"  Graph refs:       {s['graph_refs']}")
        print(f"  Cross-graph edges:{s['cross_edges']}")
        print(f"  Meta-graph edges: {s['meta_edges']}")


if __name__ == "__main__":
    main()
