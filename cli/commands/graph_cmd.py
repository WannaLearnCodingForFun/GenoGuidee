from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def run(args) -> int:
    from app.knowledge_graph.graph import build_gene_graph

    g = build_gene_graph(args.gene.upper())
    console.print(f"[bold cyan]Knowledge graph[/bold cyan] {g['gene']} "
                  f"({g['stats']['n_nodes']} nodes, {g['stats']['n_edges']} edges, {g['kg_version']})")
    t = Table(show_header=True)
    t.add_column("edge type"); t.add_column("target", max_width=60); t.add_column("detail")
    for e in g["edges"][:40]:
        node = next((n for n in g["nodes"] if n["id"] == e["target"]), {})
        t.add_row(e["type"], node.get("label", e["target"]),
                  e.get("classification", "") or str(node.get("ic", "")))
    console.print(t)
    return 0
