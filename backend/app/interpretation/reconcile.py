"""
ML ↔ ACMG evidence reconciliation (section 35).

Invariants (safety-tested in tests/test_safety.py):
  * final_classification is ALWAYS the ACMG classification;
  * ML output can only ADD a human-review flag, never remove one and never
    change the classification;
  * concordance is never converted into clinical certainty (note field).
"""
from __future__ import annotations

from typing import Optional

from ..schemas.interpretation import AcmgInterpretation, MlPrediction, Reconciliation

_BUCKETS = {
    "pathogenic": "pathogenic_spectrum",
    "likely_pathogenic": "pathogenic_spectrum",
    "PATHOGENIC": "pathogenic_spectrum",
    "LIKELY_PATHOGENIC": "pathogenic_spectrum",
    "Pathogenic": "pathogenic_spectrum",
    "Likely Pathogenic": "pathogenic_spectrum",
    "vus": "uncertain",
    "VUS": "uncertain",
    "likely_benign": "benign_spectrum",
    "benign": "benign_spectrum",
    "LIKELY_BENIGN": "benign_spectrum",
    "BENIGN": "benign_spectrum",
    "Likely Benign": "benign_spectrum",
    "Benign": "benign_spectrum",
}


def bucket(classification: str) -> str:
    return _BUCKETS.get(classification, "uncertain")


def reconcile(acmg: AcmgInterpretation, ml: Optional[MlPrediction]) -> Reconciliation:
    acmg_bucket = bucket(acmg.classification)
    review = acmg.human_review_required  # ML can only escalate, never clear

    if ml is None:
        return Reconciliation(
            status="ML_UNAVAILABLE", ml_bucket=None, acmg_bucket=acmg_bucket,
            final_classification=acmg.classification,
            human_review_required=True,
            note="No ML prediction available; ACMG-only interpretation — human review required.",
        )

    ml_bucket = bucket(ml.top_class)

    if ml.ood and ml.ood.get("state") == "OUT_OF_DISTRIBUTION":
        review = True
    if ml.uncertainty and ml.uncertainty.get("max_probability", 1.0) < 0.5:
        review = True

    if ml_bucket == acmg_bucket:
        status = "CONCORDANT"
        note = ("Independent ML and ACMG paths agree. Concordance does not "
                "constitute clinical certainty; interpretation remains subject "
                "to professional review.")
    else:
        status = "DISCORDANT"
        review = True
        note = (f"ML path suggests {ml_bucket} while ACMG evidence yields "
                f"{acmg_bucket}. The deterministic ACMG result stands; "
                "HUMAN REVIEW REQUIRED.")

    return Reconciliation(
        status=status, ml_bucket=ml_bucket, acmg_bucket=acmg_bucket,
        final_classification=acmg.classification,
        human_review_required=review, note=note,
    )
