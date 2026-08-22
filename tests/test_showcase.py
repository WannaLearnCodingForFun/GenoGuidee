"""Regression: legacy demo showcase variants still classify through ACMG v1."""
from app.acmg import classify
from app.dataset import SHOWCASE_VARIANTS
from app.interpretation.reconcile import bucket, reconcile
from app.ml import esm_representation, predict
from app.schemas.interpretation import AcmgInterpretation, MlPrediction


def test_eight_showcase_variants_classify():
    assert len(SHOWCASE_VARIANTS) == 8
    results = {}
    for v in SHOWCASE_VARIANTS:
        acmg = classify(v)
        results[v["id"]] = acmg["classification"]
        assert acmg["engine"] == "deterministic-rule-engine"
        assert "criteria" in acmg
    # BRCA1 founder frameshift must remain pathogenic under v1
    assert results["VAR-BRCA1-5266DUP"] == "Pathogenic"
    # Common polymorphism must remain benign (BA1)
    assert results["VAR-BRCA2-N372H"] == "Benign"
    # TP53 demo VUS remains VUS (the discordance case)
    assert results["VAR-TP53-R158H"] == "VUS"


def test_tp53_discordance_invariant():
    v = next(x for x in SHOWCASE_VARIANTS if x["id"] == "VAR-TP53-R158H")
    acmg = classify(v)
    esm = esm_representation(v)
    ml = predict(v, esm["delta_score"])
    # wrap into v2 reconciliation to prove ML cannot change ACMG
    acmg_obj = AcmgInterpretation(
        classification="VUS" if acmg["classification"] == "VUS" else acmg["classification"],
        criteria=[], met_criteria=acmg["met_criteria"], not_evaluable=[],
        rule_version="legacy-v1", combining_rationale=acmg["rule_note"],
        confidence="moderate", human_review_required=True,
    )
    ml_obj = MlPrediction(
        model_id="demo", model_version="demo",
        probabilities=ml["probabilities"], top_class=ml["top_class_key"],
        calibrated=False,
    )
    rec = reconcile(acmg_obj, ml_obj)
    assert rec.final_classification == "VUS"
    assert rec.status == "DISCORDANT"
    assert bucket(ml["top_class_key"]) == "pathogenic_spectrum"
