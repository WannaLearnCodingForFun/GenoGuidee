"""
End-to-end interpretation service: canonical variant (+ optional patient
context) → section-76 InterpretationObject.

Pipeline: evidence assembly → ACMG v2 (deterministic, authoritative) →
ML prediction (registered tabular model, calibrated, with uncertainty/OOD)
→ reconciliation (ML never overrides) → phenotype match (context only) →
knowledge-graph context → optional somatic therapy ranking (advisory,
never ACMG evidence) → clinical considerations (safety-gated) →
provenance ledger v2 record.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import numpy as np

from ..interpretation import clinical_v2, reconcile as R
from ..interpretation.acmg_v2 import RULE_VERSION, evaluate
from ..interpretation.clingen_specs import load_specification
from ..knowledge_graph.graph import KG_VERSION, _clingen_edges
from ..provenance2 import ledger
from ..schemas.interpretation import InterpretationObject, MlPrediction, ProvenanceRecord
from ..schemas.variant import CanonicalVariant
from .evidence import ANNOTATION_VERSION, EvidenceService

REPO = Path(__file__).resolve().parents[3]
MODEL_DIR = REPO / "models/production"
REGISTRY_DIR = REPO / "models/registry"

# the research package (feature schema) lives at repo root
import sys  # noqa: E402
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@lru_cache(maxsize=1)
def _load_ml_model() -> Optional[dict[str, Any]]:
    """Load the registered best tabular model, if trained."""
    if not REGISTRY_DIR.exists():
        return None
    entries = sorted(REGISTRY_DIR.glob("genoguide-tabular-*.json"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for entry_path in entries:
        meta = json.loads(entry_path.read_text())
        artifact = REPO / meta["artifact"] if meta.get("artifact") else None
        if artifact and artifact.exists():
            import joblib
            bundle = joblib.load(artifact)
            return {"meta": meta, **bundle}
    return None


def _feature_vector(annotation: dict[str, Any], features: list[str]) -> np.ndarray:
    from research.preprocessing.build_training_dataset import CONSEQUENCES, VARIANT_TYPES

    csq = annotation.get("consequence") or "unknown"
    if csq in ("splice_donor_variant", "splice_acceptor_variant"):
        csq = "splice_donor_or_acceptor"
    if csq not in CONSEQUENCES:
        csq = "unknown"
    genef = annotation.get("gene_features") or {}
    am = annotation.get("alphamissense") or {}
    vid = annotation["variant_id"]
    _, _, _, alleles = vid.split(":", 3)
    ref, alt = alleles.split(">")
    vt = ("SNV" if len(ref) == 1 and len(alt) == 1 else
          "MNV" if len(ref) == len(alt) else
          "insertion" if len(ref) < len(alt) else "deletion")

    def gf(key):
        v = genef.get(key)
        return np.nan if v is None else float(v)

    values = {
        **{f"csq_{c}": float(c == csq) for c in CONSEQUENCES},
        **{f"vt_{t}": float(t == vt) for t in VARIANT_TYPES},
        "ref_len": float(len(ref)), "alt_len": float(len(alt)),
        "len_delta": float(len(alt) - len(ref)),
        "loeuf": gf("loeuf"), "pli": gf("pli"), "mis_z": gf("mis_z"), "syn_z": np.nan,
        "gene_feat_missing": float(genef.get("loeuf") is None),
        "clingen_validity": float(genef.get("clingen_validity") or 0),
        "clingen_n_diseases": float(genef.get("clingen_n_diseases") or 0),
        "am_pathogenicity": (float(am["am_pathogenicity"])
                             if am.get("am_pathogenicity") is not None else np.nan),
        "am_missing": float(am.get("am_pathogenicity") is None),
    }
    pop = annotation.get("population") or {}
    af_max = pop.get("af_max")
    values["log10_af"] = float(np.log10(af_max)) if af_max else np.nan
    values["af_missing"] = float(af_max is None)
    values["is_rare"] = float(af_max is not None and af_max < 1e-4)
    return np.array([[values[f] for f in features]], dtype=np.float32)


def _ml_predict(annotation: dict[str, Any]) -> Optional[MlPrediction]:
    bundle = _load_ml_model()
    if bundle is None:
        return None
    X = _feature_vector(annotation, bundle["features"])
    proba = bundle["model"].predict_proba(X)
    # temperature calibration
    T = bundle.get("temperature", 1.0)
    logp = np.log(np.clip(proba, 1e-12, 1.0)) / T
    logp -= logp.max(axis=1, keepdims=True)
    cal = np.exp(logp)
    cal /= cal.sum(axis=1, keepdims=True)

    labels = bundle["labels"]
    p = cal[0]
    entropy = float(-(p * np.log(np.clip(p, 1e-12, 1))).sum())
    ood_state, ood_detail = "IN_DISTRIBUTION", {}
    if bundle.get("ood") is not None:
        try:
            d = float(bundle["ood"].distance(X)[0])
            ood_state = bundle["ood"].state(X)[0]
            ood_detail = {"mahalanobis": round(d, 3), **bundle["ood"].to_dict()}
        except Exception:  # noqa: BLE001 — OOD failure must not block interpretation
            ood_state = "OOD_CHECK_FAILED"

    return MlPrediction(
        model_id=bundle["meta"]["model_id"],
        model_version=bundle["meta"].get("registered", "unknown"),
        probabilities={l: round(float(x), 4) for l, x in zip(labels, proba[0])},
        top_class=labels[int(np.argmax(p))],
        calibrated=True,
        calibrated_probabilities={l: round(float(x), 4) for l, x in zip(labels, p)},
        uncertainty={"entropy": round(entropy, 4),
                     "max_probability": round(float(p.max()), 4)},
        ood={"state": ood_state, **ood_detail},
    )


class InterpretationService:
    def __init__(self) -> None:
        self.evidence = EvidenceService()

    def interpret(
        self,
        variant: CanonicalVariant,
        patient: Optional[dict[str, Any]] = None,
        record_provenance: bool = True,
        operator: str = "genoguide-engine",
        include_somatic_therapy: bool = False,
        oncology_indication: Optional[str] = None,
    ) -> InterpretationObject:
        annotation = self.evidence.annotate(variant)
        gene = annotation.get("gene") or variant.gene

        # deterministic path
        spec = load_specification(gene)
        acmg = evaluate(self.evidence.to_evidence_inputs(annotation), spec)

        # independent ML path (may be absent — that is a valid state)
        ml = _ml_predict(annotation)
        recon = R.reconcile(acmg, ml)

        # context layers (never feed ACMG)
        phenotype_match: dict[str, Any] = {"availability": "NOT_AVAILABLE",
                                           "reason": "no patient HPO terms provided"}
        if patient and patient.get("hpo_terms") and gene:
            from ..phenotype.similarity import match_patient_to_gene
            phenotype_match = match_patient_to_gene(patient["hpo_terms"], gene)

        gd_edges = [e for e in _clingen_edges() if e["gene"] == gene] if gene else []
        gene_disease_context = {
            "gene": gene,
            "clingen_associations": gd_edges[:10],
            "modes_of_inheritance": sorted({e["moi"] for e in gd_edges if e["moi"]}),
            "source": "ClinGen gene-validity (CC0)" if gd_edges else "no curated association",
        }

        # Optional somatic oncology ranking — AFTER ACMG/ML, never as evidence.
        indication = oncology_indication or (patient or {}).get("oncology_indication")
        from .drug_recommendation import resolve_somatic_therapy
        somatic_therapy = resolve_somatic_therapy(
            gene=gene,
            hgvs_p=variant.hgvs_p,
            variant_context=variant.variant_context,
            include=include_somatic_therapy,
            oncology_indication=indication,
            human_review_required=recon.human_review_required or acmg.human_review_required,
        )

        has_patient = bool(patient)
        considerations = clinical_v2.generate_considerations(
            acmg, recon, phenotype_match if has_patient else None,
            gene_disease_context, has_provenance=record_provenance,
            has_patient_context=has_patient, ml=ml,
            somatic_therapy=somatic_therapy.model_dump(mode="json"))

        uncertainty: dict[str, Any] = {
            "ml": (ml.uncertainty if ml else None),
            "ood": (ml.ood if ml else None),
            "acmg_confidence": acmg.confidence,
            "not_evaluable_criteria": len(acmg.not_evaluable),
        }
        human_review = {
            "required": recon.human_review_required,
            "reasons": [r for r, cond in [
                ("discordant ML/ACMG", recon.status == "DISCORDANT"),
                ("ML unavailable", recon.status == "ML_UNAVAILABLE"),
                ("ACMG flagged review", acmg.human_review_required),
                ("classification is VUS", acmg.classification == "VUS"),
            ] if cond],
        }

        provenance = None
        if record_provenance:
            output_payload = {"classification": acmg.classification,
                              "met": acmg.met_criteria,
                              "reconciliation": recon.status}
            rec = ledger.record_interpretation(
                input_hash=variant.input_hash,
                output_hash=ledger.sha256(json.dumps(output_payload, sort_keys=True)),
                annotation_version=ANNOTATION_VERSION,
                model_version=(ml.model_id if ml else None),
                model_hash=(_load_ml_model() or {}).get("meta", {}).get("artifact_sha256"),
                acmg_rule_version=RULE_VERSION,
                knowledge_graph_version=KG_VERSION,
                phenotype_version=phenotype_match.get("hpo_version"),
                evidence_snapshot=annotation,
                operator=operator,
            )
            provenance = ProvenanceRecord(
                interpretation_id=rec["interpretation_id"],
                input_hash=rec["input_hash"], output_hash=rec["output_hash"],
                annotation_version=rec["annotation_version"],
                model_version=rec["model_version"], model_hash=rec["model_hash"],
                acmg_rule_version=rec["acmg_rule_version"],
                knowledge_graph_version=rec["knowledge_graph_version"],
                phenotype_version=rec["phenotype_version"],
                evidence_snapshot_hash=rec["evidence_snapshot_hash"],
                timestamp=str(rec["timestamp"]), operator=rec["operator"],
                tx_id=rec["tx_id"],
            )

        return InterpretationObject(
            variant=variant,
            annotation={"gene": gene, "consequence": annotation["consequence"],
                        "clinvar": annotation["clinvar"],
                        "annotation_version": ANNOTATION_VERSION,
                        "sources": annotation["sources"]},
            population_evidence=(
                {"availability": "AVAILABLE", **annotation["population"]}
                if annotation.get("population") is not None
                else {"availability": "SOURCE_NOT_CONFIGURED",
                      "note": "run population_af preprocessing or configure gnomAD"}),
            functional_evidence={"alphamissense": annotation["alphamissense"],
                                 "availability": "AVAILABLE" if annotation["alphamissense"]
                                 else ("SOURCE_NOT_CONFIGURED"
                                       if annotation["sources"]["alphamissense"] != "AVAILABLE"
                                       else "NOT_AVAILABLE")},
            sequence_model={"availability": "NOT_IMPLEMENTED",
                            "note": "ESM-2 delta embeddings require a protein sequence source; "
                                    "see research/training/esm_representation.py"},
            ml_prediction=ml,
            acmg_interpretation=acmg,
            reconciliation=recon,
            phenotype_match=phenotype_match,
            gene_disease_context=gene_disease_context,
            clinical_evidence={"gene_mechanism": annotation.get("gene_mechanism"),
                               "protein_lookup": annotation.get("protein_lookup")},
            clinical_considerations=considerations,
            somatic_therapy=somatic_therapy,
            uncertainty=uncertainty,
            human_review=human_review,
            provenance=provenance,
        )
