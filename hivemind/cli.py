import argparse
import sys

from .config import load as load_config
from .hive_mind import HiveMind


def main() -> None:
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

    p_import = sub.add_parser("import",
                               help="Import an arxiv-to-obsidian knowledge graph")
    p_import.add_argument("path", help="Path to arxiv-to-obsidian project directory")
    p_import.add_argument("--name", "-n", help="Hive name (default: dir basename)")

    p_serve = sub.add_parser("serve", help="Start web dashboard")
    p_serve.add_argument("--port", "-p", type=int, default=9090,
                         help="Port (default 9090)")
    p_serve.add_argument("--host", type=str, default="127.0.0.1",
                         help="Host (default 127.0.0.1)")

    p_inspect = sub.add_parser("inspect", help="Show detailed info about a hive")
    p_inspect.add_argument("name", help="Hive name")

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
