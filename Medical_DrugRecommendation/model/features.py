"""Feature engineering module for candidate drug relevance ML model."""

from __future__ import annotations

from typing import Any

from recommendation.candidate_generator import CandidateDrug

FEATURE_NAMES: list[str] = [
    "civic_evidence_count",
    "count_level_a",
    "count_level_b",
    "count_level_c",
    "count_level_d",
    "sensitivity_ratio",
    "resistance_ratio",
    "max_rating",
    "mean_rating",
    "dgidb_interaction_present",
    "dgidb_interaction_score",
    "dgidb_evidence_score",
    "drug_is_approved",
    "drug_is_antineoplastic",
    "is_inhibitor",
]


def extract_candidate_features(candidate: CandidateDrug) -> list[float]:
    """Extract a 15-dimensional numeric feature vector for a candidate drug."""
    civic_ev = candidate.civic_evidence
    ev_count = len(civic_ev)

    count_a = 0
    count_b = 0
    count_c = 0
    count_d = 0
    sens_count = 0
    res_count = 0
    ratings: list[float] = []

    for ev in civic_ev:
        lvl = ev.evidence_level.upper()
        if lvl == "A":
            count_a += 1
        elif lvl == "B":
            count_b += 1
        elif lvl == "C":
            count_c += 1
        elif lvl == "D":
            count_d += 1

        sig = ev.significance.lower()
        if "sensitivity" in sig or "response" in sig or "positive" in sig:
            sens_count += 1
        elif "resistance" in sig or "reduced" in sig or "negative" in sig:
            res_count += 1

        if ev.rating > 0:
            ratings.append(ev.rating)

    sens_ratio = (sens_count / ev_count) if ev_count > 0 else 0.0
    res_ratio = (res_count / ev_count) if ev_count > 0 else 0.0
    max_rat = max(ratings) if ratings else 0.0
    mean_rat = (sum(ratings) / len(ratings)) if ratings else 0.0

    has_int = 1.0 if candidate.dgidb_interaction else 0.0
    int_score = candidate.dgidb_interaction.interaction_score if candidate.dgidb_interaction else 0.0
    dgidb_ev_score = float(candidate.dgidb_interaction.evidence_score) if candidate.dgidb_interaction else 0.0

    is_approved = 0.0
    if candidate.dgidb_interaction and candidate.dgidb_interaction.drug_is_approved:
        is_approved = 1.0
    elif candidate.dgidb_info and candidate.dgidb_info.approved:
        is_approved = 1.0

    is_anti = 0.0
    if candidate.dgidb_interaction and candidate.dgidb_interaction.drug_is_antineoplastic:
        is_anti = 1.0
    elif candidate.dgidb_info and candidate.dgidb_info.anti_neoplastic:
        is_anti = 1.0

    is_inhibitor = 0.0
    if candidate.dgidb_interaction:
        for t in candidate.dgidb_interaction.interaction_types:
            if "inhibitor" in t.lower() or "antagonist" in t.lower() or "binder" in t.lower():
                is_inhibitor = 1.0
                break

    return [
        float(ev_count),
        float(count_a),
        float(count_b),
        float(count_c),
        float(count_d),
        float(sens_ratio),
        float(res_ratio),
        float(max_rat),
        float(mean_rat),
        has_int,
        float(int_score),
        dgidb_ev_score,
        is_approved,
        is_anti,
        is_inhibitor,
    ]
