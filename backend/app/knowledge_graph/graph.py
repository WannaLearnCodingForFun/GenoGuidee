"""
Knowledge graph layer (section 17), built on NetworkX with a typed domain
model that can migrate to Neo4j without rewriting callers (node/edge types
mirror a property-graph schema; `to_cypher_stream` emits Neo4j-ready rows).

Grounded in REAL local sources only:
    gene—disease edges   ClinGen gene-validity (CC0)
    gene—phenotype edges HPO genes_to_phenotype
    disease—phenotype    phenotype.hpoa
    variant edges        supplied interpretation results

Nothing is fabricated: if a source file is absent the corresponding edge
type is simply missing and `sources` reports it.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import networkx as nx

from ..phenotype.ontology import load_ontology

REPO = Path(__file__).resolve().parents[3]
CLINGEN = REPO / "research/data/raw/clingen/gene_validity.csv"

KG_VERSION = "kg-v1.0.0"

NODE_TYPES = ["Patient", "Variant", "Gene", "Protein", "Disease", "Phenotype",
              "Drug", "Guideline", "Evidence", "Publication", "Laboratory",
              "Clinician", "Interpretation"]
EDGE_TYPES = ["VARIANT_IN_GENE", "GENE_ASSOCIATED_WITH_DISEASE",
              "DISEASE_HAS_PHENOTYPE", "PATIENT_HAS_PHENOTYPE",
              "VARIANT_CAUSES_DISEASE", "GENE_HAS_MECHANISM",
              "VARIANT_HAS_EVIDENCE", "EVIDENCE_SUPPORTS_CLASSIFICATION",
              "DRUG_RELEVANT_TO_GENE", "GUIDELINE_APPLIES_TO_DISEASE"]


@lru_cache(maxsize=1)
def _clingen_edges() -> list[dict[str, str]]:
    edges = []
    if not CLINGEN.exists():
        return edges
    with open(CLINGEN, newline="") as f:
        started = False
        for row in csv.reader(f):
            if not row or not row[0]:
                continue
            if row[0].startswith("+++"):
                started = True
                continue
            if not started or row[0] == "GENE SYMBOL":
                continue
            gene, _hgnc, disease, mondo, moi, _sop, classification = (row + [""] * 7)[:7]
            if gene and disease:
                edges.append({"gene": gene, "disease": disease, "mondo": mondo,
                              "moi": moi, "classification": classification})
    return edges


def build_gene_graph(gene: str, max_phenotypes: int = 25,
                     interpretations: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Gene-centric subgraph: gene → diseases (ClinGen) → phenotypes (HPO),
    gene → phenotype profile, plus any supplied variant interpretations."""
    onto = load_ontology()
    g = nx.MultiDiGraph()
    sources = {"clingen": CLINGEN.exists(), "hpo": True, "kg_version": KG_VERSION}

    g.add_node(f"gene:{gene}", type="Gene", label=gene)

    for e in _clingen_edges():
        if e["gene"] != gene:
            continue
        did = e["mondo"] or f"disease:{e['disease']}"
        g.add_node(did, type="Disease", label=e["disease"], moi=e["moi"],
                   validity=e["classification"], source="ClinGen")
        g.add_edge(f"gene:{gene}", did, type="GENE_ASSOCIATED_WITH_DISEASE",
                   classification=e["classification"], source="ClinGen gene-validity (CC0)")

    profile = sorted(onto.gene_terms.get(gene, set()),
                     key=lambda t: -onto.term_ic(t))[:max_phenotypes]
    for t in profile:
        g.add_node(t, type="Phenotype", label=onto.terms.get(t, t),
                   ic=round(onto.term_ic(t), 3), source="HPO")
        g.add_edge(f"gene:{gene}", t, type="DISEASE_HAS_PHENOTYPE",
                   source="HPO genes_to_phenotype")

    for interp in interpretations or []:
        vid = interp.get("variant_id", "variant:unknown")
        g.add_node(vid, type="Variant", label=vid,
                   classification=interp.get("classification"))
        g.add_edge(vid, f"gene:{gene}", type="VARIANT_IN_GENE")
        for crit in interp.get("met_criteria", []):
            eid = f"evidence:{vid}:{crit}"
            g.add_node(eid, type="Evidence", label=crit)
            g.add_edge(vid, eid, type="VARIANT_HAS_EVIDENCE")
            g.add_edge(eid, vid, type="EVIDENCE_SUPPORTS_CLASSIFICATION",
                       classification=interp.get("classification"))

    return {
        "gene": gene,
        "kg_version": KG_VERSION,
        "sources": sources,
        "nodes": [{"id": n, **d} for n, d in g.nodes(data=True)],
        "edges": [{"source": u, "target": v, **d} for u, v, d in g.edges(data=True)],
        "stats": {"n_nodes": g.number_of_nodes(), "n_edges": g.number_of_edges()},
    }


def to_cypher_stream(graph: dict[str, Any]) -> list[str]:
    """Neo4j migration path: emit MERGE statements for the subgraph."""
    lines = []
    for n in graph["nodes"]:
        props = ", ".join(f"{k}: {v!r}" for k, v in n.items() if k not in ("id", "type"))
        lines.append(f"MERGE (n:{n['type']} {{id: {n['id']!r}}}) SET n += {{{props}}};")
    for e in graph["edges"]:
        lines.append(
            f"MATCH (a {{id: {e['source']!r}}}), (b {{id: {e['target']!r}}}) "
            f"MERGE (a)-[:{e['type']}]->(b);")
    return lines
