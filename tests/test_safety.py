"""Safety: ML never overrides ACMG; unknown ≠ benign; OOD escalates review."""
from app.interpretation.acmg_v2 import EvidenceInputs, evaluate
from app.interpretation.reconcile import reconcile
from app.schemas.interpretation import MlPrediction


def _acmg_vus():
    return evaluate(EvidenceInputs())


def _ml(top: str, ood="IN_DISTRIBUTION", max_p=0.9):
    return MlPrediction(
        model_id="test", model_version="t",
        probabilities={top: max_p}, top_class=top,
        calibrated=True,
        calibrated_probabilities={top: max_p},
        uncertainty={"max_probability": max_p, "entropy": 0.2},
        ood={"state": ood},
    )


def test_ml_cannot_override_acmg_classification():
    acmg = _acmg_vus()
    rec = reconcile(acmg, _ml("pathogenic"))
    assert rec.final_classification == acmg.classification == "VUS"
    assert rec.status == "DISCORDANT"
    assert rec.human_review_required is True


def test_concordance_does_not_clear_review_on_vus():
    acmg = _acmg_vus()
    rec = reconcile(acmg, _ml("vus"))
    assert rec.status == "CONCORDANT"
    assert rec.final_classification == "VUS"
    # VUS already requires review from the engine
    assert rec.human_review_required is True


def test_ml_unavailable_requires_review():
    rec = reconcile(_acmg_vus(), None)
    assert rec.status == "ML_UNAVAILABLE"
    assert rec.final_classification == "VUS"
    assert rec.human_review_required is True


def test_ood_triggers_review():
    rec = reconcile(_acmg_vus(), _ml("vus", ood="OUT_OF_DISTRIBUTION"))
    assert rec.human_review_required is True


def test_unknown_variant_is_not_benign():
    r = evaluate(EvidenceInputs())
    assert r.classification != "BENIGN"
    assert r.classification == "VUS"
