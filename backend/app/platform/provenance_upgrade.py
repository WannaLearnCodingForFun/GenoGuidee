"""Provenance object for new interpretation versions. Complements ledger v1/v2; does not replace them."""
from __future__ import annotations

from typing import Any, Optional

from .evidence_graph import KG_VERSION


def build_provenance(obj: Any, operator: str = "genoguide-engine",
                     reviewer: Optional[str] = None) -> dict[str, Any]:
    prov = obj.provenance
    ml = obj.ml_prediction
    acmg = obj.acmg_interpretation
    return {
        "input_hash": getattr(prov, "input_hash", None) or getattr(obj.variant, "input_hash", None),
        "variant_hash": getattr(obj.variant, "input_hash", None),
        "annotation_version": getattr(prov, "annotation_version", None),
        "ClinVar_version": ((obj.annotation or {}).get("sources") or {}).get("clinvar"),
        "gnomAD_version": ((obj.annotation or {}).get("sources") or {}).get("gene_constraint"),
        "HPO_version": (obj.phenotype_match or {}).get("hpo_version"),
        "model_version": getattr(prov, "model_version", None) or (ml.model_version if ml else None),
        "model_hash": getattr(prov, "model_hash", None),
        "ACMG_rule_version": getattr(prov, "acmg_rule_version", None) or (acmg.rule_version if acmg else None),
        "knowledge_graph_version": getattr(prov, "knowledge_graph_version", None) or KG_VERSION,
        "evidence_snapshot": getattr(prov, "evidence_snapshot_hash", None),
        "phenotype_snapshot": (obj.phenotype_match or {}).get("score"),
        "output_hash": getattr(prov, "output_hash", None),
        "timestamp": getattr(prov, "timestamp", None),
        "operator": getattr(prov, "operator", None) or operator,
        "reviewer": reviewer,
        "ledger_tx_id": getattr(prov, "tx_id", None),
        "interpretation_id": getattr(prov, "interpretation_id", None),
    }
