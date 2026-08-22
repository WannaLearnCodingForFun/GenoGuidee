"""Unit tests for ML feature extraction and model prediction."""

from __future__ import annotations

import os
import pickle
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from model.features import extract_candidate_features
from recommendation.candidate_generator import CandidateGenerator


def test_feature_extraction() -> None:
    gen = CandidateGenerator()
    cands = gen.generate_candidates("EGFR", "L858R", "NSCLC")
    osim_cand = cands.get("osimertinib")
    assert osim_cand is not None

    feats = extract_candidate_features(osim_cand)
    assert len(feats) == 15
    assert feats[0] > 0  # civic_evidence_count


def test_model_artifact() -> None:
    model_path = os.path.join(os.path.dirname(__file__), "..", "model", "model.pkl")
    assert os.path.exists(model_path)
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    assert hasattr(model, "predict_proba")
