import json
import os
from typing import Any


def export_jsonld(kg, graph_id: str = "") -> dict:
    nodes = []
    edges = []
    for n, d in kg.graph.nodes(data=True):
        node = {
            "@id": f"hivemind:{graph_id}:{n}",
            "@type": f"hivemind:{d.get('type', 'node')}",
            "label": d.get("label", n),
        }
        if d.get("definition"):
            node["definition"] = d["definition"]
        if d.get("arxiv_id"):
            node["arxiv_id"] = d["arxiv_id"]
        if d.get("authors"):
            node["authors"] = d["authors"]
        nodes.append(node)

    for u, v, d in kg.graph.edges(data=True):
        edges.append({
            "@id": f"hivemind:{graph_id}:edge:{u}->{v}",
            "@type": "hivemind:relation",
            "source": f"hivemind:{graph_id}:{u}",
            "target": f"hivemind:{graph_id}:{v}",
            "relation": d.get("relation", "related_to"),
            "cross_graph": d.get("cross_graph", False),
            "target_graph": d.get("target_graph", ""),
        })

    context = {
        "@context": {
            "hivemind": "https://hivemind.local/ns/",
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "label": "rdfs:label",
            "definition": "rdfs:comment",
        }
    }
    return {
        **context,
        "@graph": nodes + edges,
    }


def export_obsidian(kg, graph_id: str = "",
                    output_dir: str | None = None) -> dict[str, str]:
    files: dict[str, str] = {}

    for n, d in kg.graph.nodes(data=True):
        ntype = d.get("type", "unknown")
        label = d.get("label", n)
        safe = _obsidian_safe(label)
        lines = [
            f"# {label}",
            f"type:: {ntype}",
            f"graph_id:: {graph_id}",
        ]
        if d.get("definition"):
            lines.append("")
            lines.append(d["definition"])
        if d.get("abstract"):
            lines.append("")
            lines.append(f"> {d['abstract']}")
        if d.get("arxiv_id"):
            lines.append("")
            lines.append(f"arXiv:: [{d['arxiv_id']}](https://arxiv.org/abs/{d['arxiv_id']})")
        if d.get("authors"):
            lines.append(f"authors:: {d['authors']}")

        # Find related nodes
        related = []
        for u, v, ed in kg.graph.edges(data=True):
            if u == n and kg.graph.has_node(v):
                rel_label = kg.graph.nodes[v].get("label", v)
                relation = ed.get("relation", "related_to")
                related.append(f"  - {relation}:: [[{_obsidian_safe(rel_label)}]]")
            elif v == n and kg.graph.has_node(u):
                rel_label = kg.graph.nodes[u].get("label", u)
                relation = ed.get("relation", "related_to")
                related.append(f"  - {relation}:: [[{_obsidian_safe(rel_label)}]]")

        if related:
            lines.append("")
            lines.append("## Connections")
            lines.extend(related)

        lines.append("")
        files[safe] = "\n".join(lines)

    if output_dir:
        out = os.path.join(output_dir, graph_id)
        os.makedirs(out, exist_ok=True)
        for fname, content in files.items():
            path = os.path.join(out, f"{fname}.md")
            with open(path, "w") as f:
                f.write(content)

    return files


def _obsidian_safe(name: str) -> str:
    safe = name.strip().replace("/", "-").replace(":", "-")
    return safe if safe else "untitled"
