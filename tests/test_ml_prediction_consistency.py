"""Single source of truth: predicted_class == argmax(probabilities)."""
from app.services.ml_predict import finalize_prediction, smoke_inference


def test_finalize_argmax_matches_confidence():
    pred = finalize_prediction(
        {"pathogenic": 0.676, "likely_pathogenic": 0.321, "vus": 0.002,
         "likely_benign": 0.0005, "benign": 0.0005},
        model_name="test",
        model_version="t",
        dataset_version="t",
        feature_schema_version="t",
        calibrated=True,
    )
    top = max(pred["probabilities"], key=pred["probabilities"].get)
    assert pred["predicted_class"] == top
    assert pred["confidence"] == pred["probabilities"][top]
    assert abs(sum(pred["probabilities"].values()) - 1.0) < 1e-6
    assert pred["top_class_key"] == pred["predicted_class"]


def test_production_model_can_infer():
    smoke = smoke_inference()
    assert smoke["ok"] is True


def test_interpret_prediction_is_internally_consistent():
    from app.schemas.variant import CanonicalVariant, GenomeBuild
    from app.services.interpret import InterpretationService

    cv = CanonicalVariant.from_vcf_fields(
        GenomeBuild.GRCH38, "17", 43057062, "T", "TG",
    )
    obj = InterpretationService().interpret(cv, record_provenance=False)
    ml = obj.ml_prediction
    if ml is None:
        return
    probs = ml.calibrated_probabilities or ml.probabilities
    top = max(probs, key=probs.get)
    assert ml.top_class == top
    assert abs(sum(probs.values()) - 1.0) < 1e-4
