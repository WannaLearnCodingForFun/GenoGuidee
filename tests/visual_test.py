# tests/visual_test.py
r"""
Local visual smoke test for graph_builders.py -- renders each graph type
to standalone HTML you can open in a browser.

Usage (from repo root, e.g. C:\Users\you\genochain):
    python tests\visual_test.py carrier
    python tests\visual_test.py trio
    python tests\visual_test.py cohort
    python tests\visual_test.py all
"""
from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from pyvis.network import Network

# repo root = parent of this file's parent (tests/ -> repo root)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.family.carrier_screen import CarrierVariant, screen_couple
from src.family.trio_phasing import Variant, phase_trio
from src.visualization.graph_builders import carrier_network_graph, trio_pedigree_graph

OUT_DIR = Path(__file__).resolve().parent / "visual_out"
OUT_DIR.mkdir(exist_ok=True)

_KIND_COLOR = {
    "partner": "#4C72B0",
    "flagged_gene": "#C44E52",
    "variant": "#8172B2",
    "parent": "#4C72B0",
    "child": "#55A868",
    "root": "#333333",
    "rule_path": "#DD8452",
    "ml_path": "#8172B2",
    "convergence": "#55A868",
    "divergence": "#C44E52",
    "incomplete": "#999999",
}


def render(graph: dict, filename: str, title: str = "") -> Path:
    net = Network(height="800px", width="100%", directed=True, notebook=False)
    net.barnes_hut(spring_length=220, spring_strength=0.015, damping=0.9)

    for n in graph["nodes"]:
        color = _KIND_COLOR.get(n.get("kind"), "#AAAAAA")
        if n.get("high_priority") or n.get("status") == "disagree":
            color = "#B22222"
        elif n.get("kind") == "variant" and n.get("is_pathogenic") is False:
            color = "#CCCCCC"   # dim non-pathogenic de novo / benign-context variants
        size = 30 if n.get("kind") in ("partner", "parent", "child", "root") else 18
        title_lines = [f"{k}: {v}" for k, v in n.items() if k not in ("id", "label")]
        net.add_node(
            n["id"], label=str(n.get("label", n["id"])), color=color, size=size,
            title="\n".join(title_lines),
            font={"size": 16, "strokeWidth": 3, "strokeColor": "#ffffff"},  # readable over crowded layouts
        )

    for l in graph["links"]:
        net.add_edge(l["source"], l["target"], title=l.get("kind", ""), arrowStrikethrough=False)

    net.set_options("""
    {
      "physics": { "stabilization": { "iterations": 300 } },
      "edges": { "smooth": false, "arrows": { "to": { "enabled": true, "scaleFactor": 0.6 } } },
      "layout": { "improvedLayout": true }
    }
    """)
    out_path = OUT_DIR / filename
    net.write_html(str(out_path), notebook=False)
    print(f"[{title or graph.get('chart_type')}] {len(graph['nodes'])} nodes, "
          f"{len(graph['links'])} links -> {out_path}")
    return out_path

# ---------------------------------------------------------------------------
# Fixture: single realistic couple
# ---------------------------------------------------------------------------

def fixture_couple():
    partner_a = [
        CarrierVariant("CFTR", "c.1521_1523delCTT", "Pathogenic"),
        CarrierVariant("HBB", "c.20A>T", "Pathogenic"),
        CarrierVariant("GJB2", "c.35delG", "Pathogenic"),
        CarrierVariant("PAH", "c.1222C>T", "Likely Pathogenic"),   # single-carrier, not flagged
        CarrierVariant("GBA", "c.1226A>G", "Likely Pathogenic"),   # single-carrier, not flagged
    ]
    partner_b = [
        CarrierVariant("CFTR", "c.1652G>A", "Pathogenic"),          # compound het w/ A
        CarrierVariant("HBB", "c.20A>T", "Pathogenic"),             # same variant as A
        CarrierVariant("GJB2", "c.101T>C", "Pathogenic"),           # compound het w/ A
        CarrierVariant("ATP7B", "c.3207C>A", "Likely Pathogenic"),  # single-carrier, not flagged
    ]
    return screen_couple(partner_a, partner_b)


def fixture_trio():
    mother_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),
        Variant("chr11", 5227002, "A", "T", gene="HBB"),
        Variant("chr13", 20763612, "G", "T", gene="GJB2"),
    ]
    father_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),
        Variant("chr12", 102855798, "C", "T", gene="PAH"),
    ]
    child_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),
        Variant("chr11", 5227002, "A", "T", gene="HBB"),
        Variant("chr12", 102855798, "C", "T", gene="PAH"),
        Variant("chr13", 20763612, "G", "T", gene="GJB2"),
        Variant("chr17", 41244936, "G", "A", gene="BRCA1"),
        Variant("chr17", 7675088, "C", "T", gene="TP53"),
    ]
    pathogenic_lookup = {
        ("chr17", 41244936, "G", "A"): True,
        ("chr17", 7675088, "C", "T"): False,
        ("chr7", 117559590, "C", "T"): True,
    }
    return phase_trio(child_vars, mother_vars, father_vars, pathogenic_lookup)


def fixture_cohort(n_couples: int = 10):
    import random
    random.seed(7)
    panel = {
        "CFTR": ("c.1521_1523delCTT", "c.1652G>A"),
        "HBB": ("c.20A>T", "c.20A>T"),
        "GJB2": ("c.35delG", "c.101T>C"),
        "HEXA": ("c.1274_1277dupTATC", "c.1421+1G>C"),
    }
    results = []
    for i in range(n_couples):
        a, b = [], []
        for gene, (va, vb) in panel.items():
            if random.random() < 0.35:   # was 0.15 — too sparse to reliably flag
                a.append(CarrierVariant(gene, va, "Pathogenic"))
            if random.random() < 0.35:
                b.append(CarrierVariant(gene, vb, "Pathogenic"))
        results.append((f"Couple {i+1} A", f"Couple {i+1} B", screen_couple(a, b)))
    # guarantee at least 3 flagged couples so the demo never depends on luck
    for i in range(3):
        results[i] = (
            f"Couple {i+1} A", f"Couple {i+1} B",
            screen_couple(
                [CarrierVariant("CFTR", "c.1521_1523delCTT", "Pathogenic")],
                [CarrierVariant("CFTR", "c.1652G>A", "Pathogenic")],
            ),
        )
    return results

def run(which: str):
    if which in ("carrier", "all"):
        screen_result = fixture_couple()
        print(screen_result.summary())
        graph = carrier_network_graph("Partner A", "Partner B", screen_result)
        path = render(graph, "carrier_network.html", "Carrier network")
        if which == "carrier":
            webbrowser.open(path.as_uri())

    if which in ("trio", "all"):
        phasing = fixture_trio()
        print(phasing.summary())
        graph = trio_pedigree_graph(phasing, mother_label="Mother", father_label="Father", child_label="Child")
        path = render(graph, "pedigree.html", "Trio pedigree")
        if which == "trio":
            webbrowser.open(path.as_uri())

    if which in ("cohort", "all"):
        net = Network(height="900px", width="100%", notebook=False)
        seen_nodes = set()
        for a_label, b_label, screen_result in fixture_cohort():
            graph = carrier_network_graph(a_label, b_label, screen_result)
            for n in graph["nodes"]:
                if n["id"] in seen_nodes:
                    continue
                seen_nodes.add(n["id"])
                color = _KIND_COLOR.get(n.get("kind"), "#AAAAAA")
                size = 25 if n.get("kind") == "partner" else 15
                net.add_node(n["id"], label=str(n.get("label", n["id"])), color=color, size=size)
            for l in graph["links"]:
                net.add_edge(l["source"], l["target"])
        out_path = OUT_DIR / "cohort.html"
        net.write_html(str(out_path), notebook=False)
        print(f"[cohort] {len(seen_nodes)} unique nodes -> {out_path}")
        if which == "cohort":
            webbrowser.open(out_path.as_uri())


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    run(which)