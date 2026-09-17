"""End-to-end platform pipeline (variant → ACMG → graph → radar → version → reanalysis)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_pipeline_variant_to_reanalysis(client):
    from app.interpretation.acmg_v2 import EvidenceInputs, evaluate
    from app.platform.conflict_radar import aggregate
    from app.platform.evidence_graph import add_edge, upsert_node
    from app.platform import interpretations as I
    from app.platform.reanalysis import run
    from app.schemas.variant import CanonicalVariant, GenomeBuild

    cv = CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, "17", 43057062, "T", "TG")
    acmg = evaluate(EvidenceInputs())
    assert acmg.classification == "VUS"  # unknown ≠ benign
    radar = aggregate({"acmg": acmg.classification, "ml": None, "clinvar": None})
    assert radar["overall_state"] in {"MIXED", "INSUFFICIENT", "CONCORDANT"}
    upsert_node(f"variant:{cv.variant_id}", "Variant", cv.variant_id)
    upsert_node("gene:BRCA1", "Gene", "BRCA1")
    add_edge(f"variant:{cv.variant_id}", "gene:BRCA1", "VARIANT_IN_GENE",
             source="annotation", source_id=cv.variant_id, source_version="test",
             retrieved_at="2026-09-17T00:00:00+00:00", direction="STRUCTURAL")
    I.record(
        interpretation_id="INT-PIPE", classification=acmg.classification,
        acmg_criteria=acmg.model_dump(mode="json"), ml_prediction=None,
        model_version=None, phenotype_score=None, evidence_ids=[],
        kg_version="kg-evidence-v2.0.0", guideline_version=acmg.rule_version,
        variant_id=cv.variant_id,
        provenance={"input_hash": cv.input_hash, "ACMG_rule_version": acmg.rule_version},
    )
    hist = I.history("INT-PIPE")
    assert hist[0]["classification"] == "VUS"
    result = run()
    assert result["auto_finalized"] is False
    # official still VUS
    assert I.get("INT-PIPE")["classification"] == "VUS"
    # existing v1 evaluate still works
    r = client.post("/api/v1/acmg/evaluate", json={})
    assert r.json()["classification"] == "VUS"
