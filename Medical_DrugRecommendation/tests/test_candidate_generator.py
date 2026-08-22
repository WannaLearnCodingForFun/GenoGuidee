"""Unit tests for candidate drug generator."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from recommendation.candidate_generator import CandidateGenerator


def test_generate_candidates_egfr() -> None:
    gen = CandidateGenerator()
    cands = gen.generate_candidates("EGFR", "L858R", "NSCLC")
    assert len(cands) > 0
    assert "osimertinib" in cands or "erlotinib" in cands
    cand = cands.get("osimertinib") or cands.get("erlotinib")
    assert cand is not None
    assert "CIViC_variant" in cand.sources
