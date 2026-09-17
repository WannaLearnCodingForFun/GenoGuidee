"""Evidence graph with mandatory provenance on every evidence edge."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from . import store

NODE_TYPES = [
    "Patient", "Case", "Variant", "Gene", "Transcript", "Protein", "Disease",
    "Phenotype", "Evidence", "Publication", "ClinVarAssertion", "ClinGenAssertion",
    "PopulationObservation", "FunctionalStudy", "Guideline", "Drug",
    "Interpretation", "Reviewer",
]

EDGE_TYPES = [
    "PATIENT_HAS_CASE", "CASE_CONTAINS_VARIANT", "VARIANT_IN_GENE",
    "VARIANT_AFFECTS_TRANSCRIPT", "VARIANT_AFFECTS_PROTEIN",
    "VARIANT_ASSOCIATED_WITH_DISEASE", "DISEASE_HAS_PHENOTYPE",
    "PATIENT_HAS_PHENOTYPE", "VARIANT_HAS_EVIDENCE",
    "EVIDENCE_SUPPORTS_CRITERION", "EVIDENCE_CONTRADICTS_CRITERION",
    "EVIDENCE_FROM_PUBLICATION", "VARIANT_HAS_CLINVAR_ASSERTION",
    "GENE_HAS_DISEASE", "GENE_HAS_INHERITANCE", "GUIDELINE_APPLIES_TO_VARIANT",
    "GUIDELINE_APPLIES_TO_DISEASE", "INTERPRETATION_USES_EVIDENCE", "REVIEWED_BY",
]

EVIDENCE_EDGES = {
    "VARIANT_HAS_EVIDENCE", "EVIDENCE_SUPPORTS_CRITERION",
    "EVIDENCE_CONTRADICTS_CRITERION", "EVIDENCE_FROM_PUBLICATION",
    "VARIANT_HAS_CLINVAR_ASSERTION", "INTERPRETATION_USES_EVIDENCE",
}

KG_VERSION = "kg-evidence-v2.0.0"


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_node(node_key: str, node_type: str, label: str,
                properties: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if node_type not in NODE_TYPES:
        raise ValueError(f"unknown node type {node_type}")
    store.execute(
        """INSERT INTO evidence_graph_nodes (node_key, node_type, label, properties_json, created_at)
           VALUES (?,?,?,?,?)
           ON CONFLICT(node_key) DO UPDATE SET
             node_type=excluded.node_type,
             label=excluded.label,
             properties_json=excluded.properties_json""",
        (node_key, node_type, label, store.dumps(properties or {}), store.now()),
    )
    return {"key": node_key, "type": node_type, "label": label, "properties": properties or {}}


def add_edge(
    source_key: str,
    target_key: str,
    edge_type: str,
    *,
    source: Optional[str] = None,
    source_id: Optional[str] = None,
    source_version: Optional[str] = None,
    retrieved_at: Optional[str] = None,
    evidence_strength: Optional[str] = None,
    direction: Optional[str] = None,
    properties: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if edge_type not in EDGE_TYPES:
        raise ValueError(f"unknown edge type {edge_type}")
    if edge_type in EVIDENCE_EDGES:
        if not source or not retrieved_at:
            raise ValueError("evidence edges require source and retrieved_at provenance")
    retrieved_at = retrieved_at or _ts()
    store.execute(
        """INSERT INTO evidence_graph_edges
           (source_key, target_key, edge_type, source, source_id, source_version,
            retrieved_at, evidence_strength, direction, properties_json, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (source_key, target_key, edge_type, source or "structural", source_id,
         source_version, retrieved_at, evidence_strength, direction,
         store.dumps(properties or {}), store.now()),
    )
    return {
        "source_key": source_key, "target_key": target_key, "edge_type": edge_type,
        "source": source or "structural", "source_id": source_id,
        "source_version": source_version, "retrieved_at": retrieved_at,
        "evidence_strength": evidence_strength, "direction": direction,
        "version": source_version,
        "strength": evidence_strength,
    }


def subgraph(seed: str, limit: int = 200) -> dict[str, Any]:
    nodes = store.execute(
        "SELECT node_key, node_type, label, properties_json FROM evidence_graph_nodes WHERE node_key=?",
        (seed,), fetch="all",
    ) or []
    edges = store.execute(
        """SELECT source_key, target_key, edge_type, source, source_id, source_version,
                  retrieved_at, evidence_strength, direction, properties_json
           FROM evidence_graph_edges
           WHERE source_key=? OR target_key=? LIMIT ?""",
        (seed, seed, limit), fetch="all",
    ) or []
    keys = {seed}
    edge_out = []
    for e in edges:
        keys.add(e[0]); keys.add(e[1])
        edge_out.append({
            "source_key": e[0], "target_key": e[1], "edge_type": e[2],
            "source": e[3], "source_id": e[4], "source_version": e[5],
            "retrieved_at": e[6], "evidence_strength": e[7], "direction": e[8],
            "properties": store.loads(e[9], {}),
        })
    extra = []
    for k in keys:
        row = store.execute(
            "SELECT node_key, node_type, label, properties_json FROM evidence_graph_nodes WHERE node_key=?",
            (k,), fetch="one",
        )
        if row:
            extra.append({"key": row[0], "type": row[1], "label": row[2],
                          "properties": store.loads(row[3], {})})
    return {"kg_version": KG_VERSION, "seed": seed, "nodes": extra or [
        {"key": n[0], "type": n[1], "label": n[2], "properties": store.loads(n[3], {})}
        for n in nodes
    ], "edges": edge_out}


def attach_interpretation(obj: Any) -> list[str]:
    """Project an InterpretationObject into the evidence graph. Never fabricates sources."""
    from datetime import datetime, timezone
    retrieved = datetime.now(timezone.utc).isoformat()
    variant = obj.variant
    vid = variant.variant_id
    vkey = f"variant:{vid}"
    upsert_node(vkey, "Variant", vid, {"chromosome": variant.chromosome, "position": variant.position})
    gene = (obj.annotation or {}).get("gene") or variant.gene
    evidence_ids: list[str] = []
    if gene:
        gkey = f"gene:{gene}"
        upsert_node(gkey, "Gene", gene)
        add_edge(vkey, gkey, "VARIANT_IN_GENE", source="annotation",
                 source_id=vid, source_version=str((obj.annotation or {}).get("annotation_version") or "unknown"),
                 retrieved_at=retrieved, direction="STRUCTURAL")
    acmg = obj.acmg_interpretation
    if acmg:
        ikey = f"interpretation:{getattr(obj.provenance, 'interpretation_id', None) or vid}"
        upsert_node(ikey, "Interpretation", acmg.classification)
        for crit in acmg.criteria:
            status = crit.status.value if hasattr(crit.status, "value") else str(crit.status)
            if status != "MET":
                continue
            eid = f"evidence:{vid}:{crit.id}"
            upsert_node(eid, "Evidence", crit.id, {"reason": crit.reason, "sources": crit.sources})
            src = (crit.sources[0] if crit.sources else "acmg-engine")
            add_edge(vkey, eid, "VARIANT_HAS_EVIDENCE",
                     source=src, source_id=crit.id, source_version=crit.rule_version,
                     retrieved_at=crit.timestamp or retrieved,
                     evidence_strength=str(crit.applied_strength or crit.default_strength),
                     direction="SUPPORTS_PATHOGENIC" if crit.category == "pathogenic" else "SUPPORTS_BENIGN")
            add_edge(eid, ikey, "EVIDENCE_SUPPORTS_CRITERION",
                     source=src, source_id=crit.id, source_version=crit.rule_version,
                     retrieved_at=crit.timestamp or retrieved,
                     evidence_strength=str(crit.applied_strength or crit.default_strength),
                     direction="SUPPORTS_PATHOGENIC" if crit.category == "pathogenic" else "SUPPORTS_BENIGN")
            add_edge(ikey, eid, "INTERPRETATION_USES_EVIDENCE",
                     source="acmg-engine", source_id=crit.id, source_version=crit.rule_version,
                     retrieved_at=retrieved, evidence_strength=str(crit.applied_strength or ""),
                     direction="USES")
            evidence_ids.append(eid)
        clinvar = (obj.annotation or {}).get("clinvar") or {}
        if clinvar.get("clinical_significance"):
            ckey = f"clinvar:{vid}"
            upsert_node(ckey, "ClinVarAssertion", str(clinvar.get("clinical_significance")), clinvar)
            add_edge(vkey, ckey, "VARIANT_HAS_CLINVAR_ASSERTION",
                     source="ClinVar",
                     source_id=str(clinvar.get("variation_id") or clinvar.get("rcv") or vid),
                     source_version=str(clinvar.get("version") or "unknown"),
                     retrieved_at=retrieved,
                     evidence_strength=str(clinvar.get("review_status") or "UNKNOWN"),
                     direction="SUPPORTS_PATHOGENIC" if "pathogenic" in str(clinvar.get("clinical_significance")).lower()
                     else "SUPPORTS_BENIGN" if "benign" in str(clinvar.get("clinical_significance")).lower()
                     else "UNCERTAIN")
    return evidence_ids
