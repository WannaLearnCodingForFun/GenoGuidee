"""Training script for candidate drug relevance ML ranking model.

Extracts feature vectors across oncology variants in CIViC and DGIdb,
trains a Gradient Boosting classifier, and saves model.pkl.
"""

from __future__ import annotations

import os
import pickle
import sys
from typing import Any

# Ensure module root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

from model.features import FEATURE_NAMES, extract_candidate_features
from preprocessing.civic_parser import CIViCParser
from preprocessing.dgidb_parser import DGIdbParser
from recommendation.candidate_generator import CandidateGenerator


def build_training_dataset(
    civic_parser: CIViCParser, dgidb_parser: DGIdbParser
) -> tuple[np.ndarray, np.ndarray]:
    """Generate X feature matrix and y target labels from attached datasets."""
    generator = CandidateGenerator(civic_parser, dgidb_parser)

    # Core training gene & variant pairs
    training_cases = [
        ("EGFR", "L858R", "Non-Small Cell Lung Cancer"),
        ("EGFR", "T790M", "Non-Small Cell Lung Cancer"),
        ("EGFR", "Exon 19 Deletion", "Non-Small Cell Lung Cancer"),
        ("BRAF", "V600E", "Melanoma"),
        ("BRAF", "V600E", "Colorectal Cancer"),
        ("KRAS", "G12C", "Non-Small Cell Lung Cancer"),
        ("KRAS", "G12D", "Pancreatic Adenocarcinoma"),
        ("ALK", "EML4-ALK", "Non-Small Cell Lung Cancer"),
        ("ERBB2", "Amplification", "Breast Cancer"),
        ("KIT", "D816V", "Gastrointestinal Stromal Tumor"),
        ("MET", "Exon 14 Skipping", "Non-Small Cell Lung Cancer"),
        ("PIK3CA", "H1047R", "Breast Cancer"),
        ("ABL1", "T315I", "Chronic Myelogenous Leukemia"),
    ]

    X_list: list[list[float]] = []
    y_list: list[int] = []

    for gene, variant, disease in training_cases:
        candidates = generator.generate_candidates(gene, variant, disease)
        for cand in candidates.values():
            feats = extract_candidate_features(cand)
            ev_count = len(cand.civic_evidence)

            # Labeling rule:
            # Positive (1): Has level A/B CIViC sensitivity evidence OR (DGIdb approved antineoplastic inhibitor with >=1 CIViC evidence item)
            # Negative (0): Primary resistance, or low score / unapproved
            is_pos = 0
            if ev_count > 0:
                sens_cnt = sum(
                    1
                    for ev in cand.civic_evidence
                    if ("sensitivity" in ev.significance.lower() or "response" in ev.significance.lower())
                    and ev.evidence_direction.lower() != "does not support"
                )
                res_cnt = sum(
                    1
                    for ev in cand.civic_evidence
                    if ("resistance" in ev.significance.lower() or "reduced" in ev.significance.lower())
                    and ev.evidence_direction.lower() != "does not support"
                )
                if sens_cnt > res_cnt and sens_cnt >= 1:
                    is_pos = 1
            elif cand.dgidb_interaction and cand.dgidb_interaction.drug_is_approved and cand.dgidb_interaction.drug_is_antineoplastic:
                is_pos = 1

            X_list.append(feats)
            y_list.append(is_pos)

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list, dtype=np.int32)
    return X, y


def train_model() -> GradientBoostingClassifier:
    """Train Gradient Boosting model and persist to model.pkl."""
    print("Loading CIViC and DGIdb parsers...")
    civic = CIViCParser()
    civic.load_data()
    dgidb = DGIdbParser()
    dgidb.load_data()

    print("Building training feature dataset...")
    X, y = build_training_dataset(civic, dgidb)
    print(f"Dataset shape: X={X.shape}, y={y.shape}. Positive class ratio: {np.mean(y):.3f}")

    clf = GradientBoostingClassifier(
        n_estimators=100,
        learning_rate=0.08,
        max_depth=4,
        random_state=42,
    )
    clf.fit(X, y)

    y_pred = clf.predict(X)
    y_prob = clf.predict_proba(X)[:, 1]

    acc = accuracy_score(y, y_pred)
    prec = precision_score(y, y_pred, zero_division=0)
    rec = recall_score(y, y_pred, zero_division=0)
    auc = roc_auc_score(y, y_prob)

    print("=== Training Metrics ===")
    print(f"Accuracy:  {acc:.4f}")
    print(f"Precision: {prec:.4f}")
    print(f"Recall:    {rec:.4f}")
    print(f"ROC-AUC:   {auc:.4f}")

    model_dir = os.path.dirname(__file__)
    model_path = os.path.join(model_dir, "model.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(clf, f)

    print(f"Model saved successfully to {model_path}")
    return clf


if __name__ == "__main__":
    train_model()
