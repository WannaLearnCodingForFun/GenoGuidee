"""Drug Ranker module for hybrid ML + deterministic clinical evidence scoring.

Combines ML model relevance prediction with strict clinical evidence safety rules
(e.g., resistance filters and evidence level weighting) to produce final rankings.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import pickle
import sys
from typing import Any

from model.features import extract_candidate_features
from recommendation.candidate_generator import CandidateDrug
from recommendation.evidence_ranker import BaselineEvidenceRanker


@dataclass
class RankedDrugRecommendation:
    drug: str
    rank: int
    score: float
    response: str
    evidence_level: str
    evidence_count: int


class DrugRanker:
    """Hybrid ranker combining ML relevance predictions and clinical evidence rules."""

    def __init__(self, model_path: str | None = None) -> None:
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), "..", "model", "model.pkl")
        self.model_path = os.path.abspath(model_path)
        self.model = None
        self.evidence_ranker = BaselineEvidenceRanker()

    def _load_model(self) -> None:
        """Load trained ML model artifact."""
        if self.model is not None:
            return
        if os.path.exists(self.model_path):
            with open(self.model_path, "rb") as f:
                self.model = pickle.load(f)
        else:
            self.model = None

    def rank_candidates(
        self, candidates: dict[str, CandidateDrug], top_n: int = 10
    ) -> list[RankedDrugRecommendation]:
        """Rank candidate drugs using hybrid ML + clinical evidence rules."""
        self._load_model()

        scored_items: list[tuple[CandidateDrug, float, str, str, int]] = []

        for cand in candidates.values():
            base_res = self.evidence_ranker.score_candidate(cand)
            feats = extract_candidate_features(cand)

            if self.model is not None:
                ml_prob = float(self.model.predict_proba([feats])[0, 1])
            else:
                ml_prob = base_res.baseline_score

            # Hybrid Score Formulation:
            # Deterministic Safety Override:
            # If evidence base proves primary RESISTANCE, penalize ML prediction heavily.
            if base_res.is_resistant:
                final_score = min(0.05, base_res.baseline_score * 0.1)
            else:
                # Weighted blend of ML prediction and deterministic clinical evidence score
                final_score = 0.55 * ml_prob + 0.45 * base_res.baseline_score

                # Level A evidence boost
                if base_res.top_evidence_level == "A":
                    final_score += 0.05
                elif base_res.top_evidence_level == "B":
                    final_score += 0.025

            final_score = max(0.01, min(0.99, round(final_score, 4)))
            scored_items.append(
                (
                    cand,
                    final_score,
                    base_res.response_type,
                    base_res.top_evidence_level,
                    base_res.evidence_count,
                )
            )

        # Sort by final score descending, then evidence count descending
        scored_items.sort(key=lambda x: (x[1], x[4]), reverse=True)

        recommendations: list[RankedDrugRecommendation] = []
        rank = 1
        seen_drugs: set[str] = set()

        for cand, score, response, level, count in scored_items:
            d_name = cand.drug_name.strip()
            d_lower = d_name.lower()
            if d_lower in seen_drugs:
                continue
            seen_drugs.add(d_lower)

            recommendations.append(
                RankedDrugRecommendation(
                    drug=d_name,
                    rank=rank,
                    score=score,
                    response=response if response != "N/A" else "Sensitivity",
                    evidence_level=level if level != "N/A" else "B",
                    evidence_count=count,
                )
            )
            rank += 1
            if rank > top_n:
                break

        return recommendations
