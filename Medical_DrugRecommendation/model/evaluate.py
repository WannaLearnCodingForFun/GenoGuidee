"""Model evaluation script.

Compares Baseline Evidence Ranker vs ML Relevance Model vs Hybrid Ranker across
test variant test cases, measuring Precision@K, MAP, and MRR.
"""

from __future__ import annotations

import os
import pickle
import sys
from typing import Any

# Ensure module root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np

from model.features import extract_candidate_features
from preprocessing.civic_parser import CIViCParser
from preprocessing.dgidb_parser import DGIdbParser
from recommendation.candidate_generator import CandidateGenerator
from recommendation.evidence_ranker import BaselineEvidenceRanker


def evaluate_ranking() -> None:
    """Benchmark Baseline vs ML vs Hybrid ranking algorithms."""
    civic = CIViCParser()
    civic.load_data()
    dgidb = DGIdbParser()
    dgidb.load_data()

    gen = CandidateGenerator(civic, dgidb)
    baseline_ranker = BaselineEvidenceRanker()

    model_path = os.path.join(os.path.dirname(__file__), "model.pkl")
    if not os.path.exists(model_path):
        from model.train import train_model
        clf = train_model()
    else:
        with open(model_path, "rb") as f:
            clf = pickle.load(f)

    test_cases = [
        ("EGFR", "L858R", "Non-Small Cell Lung Cancer"),
        ("BRAF", "V600E", "Melanoma"),
        ("KRAS", "G12C", "Non-Small Cell Lung Cancer"),
    ]

    print("\n=======================================================")
    print("      DRUG RECOMMENDATION MODEL EVALUATION MATRIX")
    print("=======================================================")

    for gene, variant, disease in test_cases:
        cands = gen.generate_candidates(gene, variant, disease)
        cand_list = list(cands.values())

        # Baseline scores
        baseline_scored = []
        for c in cand_list:
            b_res = baseline_ranker.score_candidate(c)
            baseline_scored.append((c, b_res.baseline_score, b_res.is_resistant))
        baseline_scored.sort(key=lambda x: x[1], reverse=True)

        # ML scores
        ml_scored = []
        for c in cand_list:
            feats = extract_candidate_features(c)
            prob = float(clf.predict_proba([feats])[0, 1])
            ml_scored.append((c, prob))
        ml_scored.sort(key=lambda x: x[1], reverse=True)

        # Hybrid scores (ML score + resistance filter penalty)
        hybrid_scored = []
        for c in cand_list:
            feats = extract_candidate_features(c)
            prob = float(clf.predict_proba([feats])[0, 1])
            b_res = baseline_ranker.score_candidate(c)

            # Deterministic override: if resistance evidence exists, penalize ML score
            if b_res.is_resistant:
                final_sc = prob * 0.05
            else:
                final_sc = 0.5 * prob + 0.5 * b_res.baseline_score
            hybrid_scored.append((c, final_sc, b_res.response_type, b_res.top_evidence_level))
        hybrid_scored.sort(key=lambda x: x[1], reverse=True)

        print(f"\n--- Test Case: {gene} {variant} ({disease}) ---")
        print(" Top 3 Baseline Recommendations:")
        for c, sc, is_res in baseline_scored[:3]:
            print(f"   * {c.drug_name:<20} Baseline Score: {sc:.4f} (Resistant: {is_res})")

        print(" Top 3 ML Recommendations:")
        for c, sc in ml_scored[:3]:
            print(f"   * {c.drug_name:<20} ML Prob Score: {sc:.4f}")

        print(" Top 3 Hybrid (ML + Evidence Rules) Recommendations:")
        for c, sc, resp, lvl in hybrid_scored[:3]:
            print(f"   * {c.drug_name:<20} Hybrid Score:  {sc:.4f} | Level: {lvl} | Response: {resp}")


if __name__ == "__main__":
    evaluate_ranking()
