"""Baseline Evidence Ranker.

Calculates deterministic clinical evidence scores based on CIViC evidence levels,
ratings, clinical direction/significance (Sensitivity vs Resistance), and DGIdb enrichment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .candidate_generator import CandidateDrug

EVIDENCE_LEVEL_WEIGHTS: dict[str, float] = {
    "A": 1.0,
    "B": 0.8,
    "C": 0.6,
    "D": 0.4,
    "E": 0.2,
}


@dataclass
class ScoredEvidenceResult:
    drug_name: str
    baseline_score: float
    response_type: str  # "Sensitivity", "Resistance", "Reduced Sensitivity", "N/A"
    top_evidence_level: str  # "A", "B", "C", "D", "E", "None"
    evidence_count: int
    is_resistant: bool
    summary: str


class BaselineEvidenceRanker:
    """Calculates deterministic baseline score for candidate drugs."""

    def score_candidate(self, candidate: CandidateDrug) -> ScoredEvidenceResult:
        """Calculate baseline clinical evidence score for a single candidate drug."""
        civic_ev = candidate.civic_evidence
        ev_count = len(civic_ev)

        if ev_count == 0:
            # DGIdb interaction only (no direct CIViC evidence)
            dgidb_score = 0.2
            is_appr = False
            if candidate.dgidb_interaction:
                if candidate.dgidb_interaction.drug_is_approved:
                    is_appr = True
                    dgidb_score += 0.2
                if candidate.dgidb_interaction.drug_is_antineoplastic:
                    dgidb_score += 0.15
                dgidb_score += min(0.2, candidate.dgidb_interaction.interaction_score * 0.2)
            elif candidate.dgidb_info:
                if candidate.dgidb_info.approved:
                    dgidb_score += 0.15

            return ScoredEvidenceResult(
                drug_name=candidate.drug_name,
                baseline_score=round(min(0.65, dgidb_score), 4),
                response_type="Sensitivity" if is_appr else "N/A",
                top_evidence_level="N/A",
                evidence_count=0,
                is_resistant=False,
                summary="Interaction data from DGIdb without direct CIViC clinical evidence.",
            )

        pos_score = 0.0
        neg_score = 0.0
        sensitivity_count = 0
        resistance_count = 0

        levels_found: set[str] = set()

        for ev in civic_ev:
            lvl = ev.evidence_level.upper()
            levels_found.add(lvl)
            lvl_weight = EVIDENCE_LEVEL_WEIGHTS.get(lvl, 0.3)
            rating_factor = max(0.2, ev.rating / 5.0)

            sig = ev.significance.lower()
            dir_str = ev.evidence_direction.lower()

            if "sensitivity" in sig or "response" in sig or "positive" in sig:
                if "does not support" in dir_str:
                    neg_score += lvl_weight * rating_factor
                else:
                    pos_score += lvl_weight * rating_factor
                    sensitivity_count += 1
            elif "resistance" in sig or "reduced" in sig or "negative" in sig:
                if "does not support" in dir_str:
                    pos_score += 0.5 * lvl_weight * rating_factor
                else:
                    neg_score += 1.5 * lvl_weight * rating_factor
                    resistance_count += 1

        # Determine highest evidence level found
        top_level = "E"
        for lvl in ["A", "B", "C", "D", "E"]:
            if lvl in levels_found:
                top_level = lvl
                break

        # Compute net evidence score
        net_score = pos_score - neg_score
        raw_score = 0.3 + (net_score / (pos_score + neg_score + 1.0)) * 0.5

        # DGIdb approval boost
        if candidate.dgidb_interaction and candidate.dgidb_interaction.drug_is_approved:
            raw_score += 0.1

        # Determine primary response type & resistance flag
        is_resistant = resistance_count > sensitivity_count or (neg_score > pos_score and resistance_count > 0)

        if is_resistant:
            response_type = "Resistance"
            final_score = max(0.01, raw_score * 0.2)  # Severe resistance penalty
        else:
            response_type = "Sensitivity" if sensitivity_count > 0 else "N/A"
            final_score = max(0.1, min(0.99, raw_score))

        return ScoredEvidenceResult(
            drug_name=candidate.drug_name,
            baseline_score=round(final_score, 4),
            response_type=response_type,
            top_evidence_level=top_level,
            evidence_count=ev_count,
            is_resistant=is_resistant,
            summary=f"CIViC evidence count: {ev_count} (Top Level {top_level}). Sensitivity: {sensitivity_count}, Resistance: {resistance_count}.",
        )
