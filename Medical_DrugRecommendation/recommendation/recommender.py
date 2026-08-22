"""Core end-to-end drug recommendation pipeline orchestrator."""

from __future__ import annotations

from typing import Any

from preprocessing.civic_parser import CIViCParser
from preprocessing.dgidb_parser import DGIdbParser
from preprocessing.normalizer import normalize_payload
from recommendation.candidate_generator import CandidateGenerator
from recommendation.drug_ranker import DrugRanker


class DrugRecommenderEngine:
    """Singleton orchestrator for drug recommendation engine."""

    def __init__(
        self, civic_parser: CIViCParser | None = None, dgidb_parser: DGIdbParser | None = None
    ) -> None:
        self.civic_parser = civic_parser or CIViCParser()
        self.dgidb_parser = dgidb_parser or DGIdbParser()
        self.candidate_generator = CandidateGenerator(self.civic_parser, self.dgidb_parser)
        self.drug_ranker = DrugRanker()

    def recommend(
        self, payload: dict[str, str], top_n: int = 10
    ) -> dict[str, Any]:
        """Process mutation payload and return ranked drug recommendations.

        Input:
            {
                "gene": "EGFR",
                "variant": "L858R",
                "disease": "NSCLC"
            }

        Output:
            {
                "gene": "EGFR",
                "variant": "L858R",
                "disease": "NSCLC",
                "recommendations": [...]
            }
        """
        raw_gene = payload.get("gene", "")
        raw_variant = payload.get("variant", "")
        raw_disease = payload.get("disease", "")

        norm = normalize_payload(payload)
        gene = norm["gene"]
        variant = norm["variant"]
        disease = norm["disease"]

        candidates = self.candidate_generator.generate_candidates(gene, variant, disease)
        ranked = self.drug_ranker.rank_candidates(candidates, top_n=top_n)

        formatted_recs = [
            {
                "drug": r.drug,
                "rank": r.rank,
                "score": r.score,
                "response": r.response,
                "evidence_level": r.evidence_level,
                "evidence_count": r.evidence_count,
            }
            for r in ranked
        ]

        return {
            "gene": raw_gene or gene,
            "variant": raw_variant or variant,
            "disease": raw_disease or disease,
            "recommendations": formatted_recs,
        }


# Default global engine instance
_ENGINE: DrugRecommenderEngine | None = None


def recommend_drugs(payload: dict[str, str], top_n: int = 10) -> dict[str, Any]:
    """Top-level convenience function for generating drug recommendations."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = DrugRecommenderEngine()
    return _ENGINE.recommend(payload, top_n=top_n)
