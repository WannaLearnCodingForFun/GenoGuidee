"""Unit tests for baseline evidence ranker."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recommendation.candidate_generator import CandidateGenerator
from recommendation.evidence_ranker import BaselineEvidenceRanker


def test_baseline_evidence_ranker() -> None:
    gen = CandidateGenerator()
    cands = gen.generate_candidates("EGFR", "L858R", "NSCLC")

    ranker = BaselineEvidenceRanker()
    osim_cand = cands.get("osimertinib")
    assert osim_cand is not None

    res = ranker.score_candidate(osim_cand)
    assert res.baseline_score > 0.5
    assert res.top_evidence_level == "A"
    assert res.response_type == "Sensitivity"
