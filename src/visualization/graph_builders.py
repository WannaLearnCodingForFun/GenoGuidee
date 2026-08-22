"""
graph_builders.py — transforms pipeline results into frontend-ready JSON
structures for visualization. This module does NOT render anything — it
outputs plain dicts (JSON-serializable) shaped for common chart libraries
(D3, Recharts, vis.js, etc.) so the frontend can pick whatever renderer fits.

Four visualizations, each mapped to a natural chart type:

1. Evidence flow  -> waterfall / Sankey diagram
   Shows each ACMG criterion as a step that adds or subtracts points,
   flowing from a zero baseline to the final tier. Visually this is the
   "how did we get here" story — genuinely useful for judges since it
   makes an opaque rule-engine score explainable at a glance.

2. Dual-path reconciliation -> convergence/divergence diagram
   Two independent paths (rule engine, ML) starting from the same variant,
   flowing toward either a shared endpoint (agreement) or splitting into
   two endpoints (disagreement, flagged red). This is your "never cut"
   differentiator — worth making this the most polished visual.

3. Carrier network -> force-directed graph
   Partner A / Partner B as root nodes, connected through shared genes to
   flagged variants. Visually striking as a network graph — shared-gene
   connections between the two partners are the "aha" moment for judges.

4. Trio pedigree -> family tree with inheritance edges
   Standard mother/father/child pedigree layout, edges colored/labeled by
   inheritance origin (maternal/paternal/de novo), de novo+pathogenic nodes
   highlighted.
"""

from __future__ import annotations

from typing import Any, Optional

from src.decision.decision_mapping import EvidenceTrace
from src.family.carrier_screen import CarrierScreenResult
from src.family.trio_phasing import Origin, TrioPhasingResult
from src.reconciliation.reconcile import ReconciliationResult


# ---------------------------------------------------------------------------
# 1. Evidence flow -> waterfall / Sankey
# ---------------------------------------------------------------------------

def evidence_flow_graph(trace: EvidenceTrace) -> dict[str, Any]:
    """
    Waterfall-chart-ready structure: a baseline node, one node per criterion
    (triggered or not), and a final node. Each triggered node carries the
    delta it contributed and the running total after it, so a frontend can
    render either a waterfall bar chart or a Sankey flow.
    """
    nodes: list[dict[str, Any]] = [
        {"id": "baseline", "label": "Baseline", "value": 0, "kind": "start"}
    ]
    links: list[dict[str, Any]] = []
    prev_id = "baseline"

    for step in trace.steps:
        node_id = f"step_{step.order}_{step.code}"
        nodes.append({
            "id": node_id,
            "label": step.code,
            "triggered": step.triggered,
            "delta": step.points if step.triggered else 0,
            "running_total": step.running_total,
            "rationale": step.rationale,
            "kind": "pathogenic_evidence" if step.points > 0 else (
                "benign_evidence" if step.points < 0 else "neutral"
            ),
        })
        if step.triggered:
            links.append({
                "source": prev_id,
                "target": node_id,
                "value": abs(step.points),
                "direction": "positive" if step.points > 0 else "negative",
            })
            prev_id = node_id

    nodes.append({
        "id": "final",
        "label": trace.final_tier,
        "value": trace.final_total,
        "kind": "end",
    })
    links.append({
        "source": prev_id,
        "target": "final",
        "value": abs(trace.final_total),
        "direction": "positive" if trace.final_total >= 0 else "negative",
    })

    return {
        "chart_type": "waterfall_or_sankey",
        "nodes": nodes,
        "links": links,
        "final_tier": trace.final_tier,
        "final_total": trace.final_total,
    }


# ---------------------------------------------------------------------------
# 2. Dual-path reconciliation -> convergence/divergence diagram
# ---------------------------------------------------------------------------

def dual_path_graph(result: ReconciliationResult) -> dict[str, Any]:
    """
    Two paths flowing from a shared 'variant' root node toward either a
    shared 'agreement' endpoint or two separate flagged endpoints.
    Frontend can render this as two converging/diverging lines (think a
    simplified Sankey with 2 sources) or a branching tree diagram.
    """
    root_id = "variant"
    rule_id = "rule_path"
    ml_id = "ml_path"

    nodes: list[dict[str, Any]] = [
        {"id": root_id, "label": result.variant, "kind": "root"},
        {
            "id": rule_id,
            "label": f"Rule engine: {result.rule_result.tier}",
            "bucket": result.rule_bucket,
            "kind": "rule_path",
        },
        {
            "id": ml_id,
            "label": f"ML path ({result.ml_source}): {result.ml_tier or 'unavailable'}",
            "bucket": result.ml_bucket,
            "kind": "ml_path",
        },
    ]
    links = [
        {"source": root_id, "target": rule_id, "kind": "flow"},
        {"source": root_id, "target": ml_id, "kind": "flow"},
    ]

    if result.agreement is True:
        nodes.append({
            "id": "agreement",
            "label": f"AGREE: {result.rule_bucket}",
            "kind": "convergence",
            "status": "agree",
        })
        links.append({"source": rule_id, "target": "agreement", "kind": "converge"})
        links.append({"source": ml_id, "target": "agreement", "kind": "converge"})
    elif result.agreement is False:
        nodes.append({
            "id": "disagreement",
            "label": "DISAGREEMENT — FLAGGED FOR REVIEW",
            "kind": "divergence",
            "status": "disagree",
        })
        links.append({"source": rule_id, "target": "disagreement", "kind": "diverge"})
        links.append({"source": ml_id, "target": "disagreement", "kind": "diverge"})
    else:
        nodes.append({
            "id": "no_comparison",
            "label": "ML path unavailable — no comparison possible",
            "kind": "incomplete",
            "status": "n/a",
        })
        links.append({"source": ml_id, "target": "no_comparison", "kind": "incomplete"})

    return {
        "chart_type": "convergence_divergence",
        "nodes": nodes,
        "links": links,
        "agreement": result.agreement,
    }


# ---------------------------------------------------------------------------
# 3. Carrier network -> force-directed graph
# ---------------------------------------------------------------------------

def carrier_network_graph(
    partner_a_label: str,
    partner_b_label: str,
    screen_result: CarrierScreenResult,
) -> dict[str, Any]:
    """
    Force-directed graph: Partner A / Partner B as root nodes, gene nodes
    in the middle, variant nodes as leaves. Shared-gene paths between the
    two partners (both flagged) are visually distinct from single-partner
    carrier hits.
    """
    nodes: list[dict[str, Any]] = [
        {"id": "partner_a", "label": partner_a_label, "kind": "partner"},
        {"id": "partner_b", "label": partner_b_label, "kind": "partner"},
    ]
    links: list[dict[str, Any]] = []
    seen_genes: set[str] = set()

    for flag in screen_result.flagged_genes:
        gene_id = f"gene_{flag.gene}"
        if gene_id not in seen_genes:
            nodes.append({
                "id": gene_id,
                "label": f"{flag.gene} ({flag.disease})",
                "kind": "flagged_gene",
                "recurrence_risk_pct": flag.recurrence_risk_pct,
                "compound_het": flag.compound_het,
            })
            seen_genes.add(gene_id)

        for v in flag.partner_a_variants:
            v_id = f"var_a_{flag.gene}_{v.variant_id}"
            nodes.append({"id": v_id, "label": v.variant_id, "kind": "variant", "classification": v.classification})
            links.append({"source": "partner_a", "target": v_id, "kind": "carries"})
            links.append({"source": v_id, "target": gene_id, "kind": "in_gene"})

        for v in flag.partner_b_variants:
            v_id = f"var_b_{flag.gene}_{v.variant_id}"
            nodes.append({"id": v_id, "label": v.variant_id, "kind": "variant", "classification": v.classification})
            links.append({"source": "partner_b", "target": v_id, "kind": "carries"})
            links.append({"source": v_id, "target": gene_id, "kind": "in_gene"})

    return {
        "chart_type": "force_directed_network",
        "nodes": nodes,
        "links": links,
        "flagged_gene_count": len(screen_result.flagged_genes),
        "screened_gene_count": len(screen_result.screened_genes),
    }


# ---------------------------------------------------------------------------
# 4. Trio pedigree -> family tree with inheritance edges
# ---------------------------------------------------------------------------

_ORIGIN_EDGE_STYLE = {
    Origin.MATERNAL: "maternal",
    Origin.PATERNAL: "paternal",
    Origin.BOTH_PARENTS: "inherited_both",
    Origin.DE_NOVO: "de_novo",
}


def trio_pedigree_graph(
    phasing_result: TrioPhasingResult,
    mother_label: str = "Mother",
    father_label: str = "Father",
    child_label: str = "Child",
) -> dict[str, Any]:
    """
    Standard pedigree layout: mother + father nodes at the top, child node
    below, one edge per phased variant labeled by inheritance origin.
    De novo + pathogenic variants get a distinct 'high_priority' flag so
    the frontend can render them as a highlighted/pulsing node.
    """
    nodes: list[dict[str, Any]] = [
        {"id": "mother", "label": mother_label, "kind": "parent", "generation": 0},
        {"id": "father", "label": father_label, "kind": "parent", "generation": 0},
        {"id": "child", "label": child_label, "kind": "child", "generation": 1},
    ]
    links: list[dict[str, Any]] = [
        {"source": "mother", "target": "child", "kind": "lineage"},
        {"source": "father", "target": "child", "kind": "lineage"},
    ]

    variant_nodes = []
    for i, pv in enumerate(phasing_result.phased_variants):
        v_id = f"variant_{i}"
        gene = pv.variant.gene or "?"
        variant_nodes.append({
            "id": v_id,
            "label": f"{gene} {pv.variant.chrom}:{pv.variant.pos}{pv.variant.ref}>{pv.variant.alt}",
            "kind": "variant",
            "origin": pv.origin.value,
            "is_pathogenic": pv.is_pathogenic,
            "high_priority": pv.high_priority,
        })
        edge_style = _ORIGIN_EDGE_STYLE[pv.origin]
        if pv.origin == Origin.MATERNAL:
            links.append({"source": "mother", "target": v_id, "kind": edge_style})
        elif pv.origin == Origin.PATERNAL:
            links.append({"source": "father", "target": v_id, "kind": edge_style})
        elif pv.origin == Origin.BOTH_PARENTS:
            links.append({"source": "mother", "target": v_id, "kind": edge_style})
            links.append({"source": "father", "target": v_id, "kind": edge_style})
        else:  # de novo — no parent edge, attaches directly to child
            pass
        links.append({"source": "child", "target": v_id, "kind": "has_variant"})

    nodes.extend(variant_nodes)

    return {
        "chart_type": "pedigree_tree",
        "nodes": nodes,
        "links": links,
        "de_novo_count": len(phasing_result.de_novo_variants),
        "high_priority_count": len(phasing_result.high_priority_variants),
    }


if __name__ == "__main__":
    import json

    from src.decision.decision_mapping import build_evidence_trace
    from src.family.carrier_screen import CarrierVariant, screen_couple
    from src.family.trio_phasing import Variant, phase_trio
    from src.scoring.acmg_rules import ACMGInput, evaluate

    print("=== 1. Evidence flow graph ===")
    acmg_result = evaluate(ACMGInput(
        gene_symbol="CFTR", consequence="frameshift_variant",
        gnomad_af=0.00001, alphamissense_score=0.9,
    ))
    trace = build_evidence_trace(acmg_result)
    print(json.dumps(evidence_flow_graph(trace), indent=2)[:800], "...\n")

    print("=== 2. Dual-path graph ===")
    fake_result = ReconciliationResult(
        variant="ENST00000003084:c.1521_1523delCTT", gene_symbol="CFTR",
        consequence="frameshift_variant", gnomad_af=0.00001,
        rule_result=acmg_result, rule_bucket="pathogenic",
        ml_tier="likely_pathogenic", ml_bucket="pathogenic",
        ml_source="alphamissense_native", agreement=True,
    )
    print(json.dumps(dual_path_graph(fake_result), indent=2)[:800], "...\n")

    print("=== 3. Carrier network graph ===")
    a_vars = [CarrierVariant("CFTR", "c.1521_1523delCTT", "Pathogenic")]
    b_vars = [CarrierVariant("CFTR", "c.1652G>A", "Pathogenic")]
    screen_result = screen_couple(a_vars, b_vars)
    print(json.dumps(carrier_network_graph("Partner A", "Partner B", screen_result), indent=2)[:800], "...\n")

    print("=== 4. Trio pedigree graph ===")
    mother_vars = [Variant("chr7", 117559590, "C", "T", gene="CFTR")]
    father_vars = [Variant("chr7", 117559590, "C", "T", gene="CFTR")]
    child_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),
        Variant("chr17", 41244936, "G", "A", gene="BRCA1"),
    ]
    phasing_result = phase_trio(
        child_vars, mother_vars, father_vars,
        {("chr17", 41244936, "G", "A"): True},
    )
    print(json.dumps(trio_pedigree_graph(phasing_result), indent=2)[:800], "...")
