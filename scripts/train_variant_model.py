#!/usr/bin/env python3
"""Train ClinVar XGBoost on a leakage-safe high-review subset.

Task A (headline 85% target): binary pathogenic-spectrum vs benign-spectrum
on review-tier >= 2, VUS/conflicts excluded, gene-disjoint split.

Task B (UI 5-class): evaluate the existing production XGBoost; do not claim
5-class accuracy of 85% if it is not.

Never uses ClinVar review status / clinsig text as features.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.evaluation.leakage import assert_no_severe_leakage, audit_split  # noqa: E402
from research.evaluation.splits import gene_disjoint_split, random_split  # noqa: E402
from research.preprocessing.build_training_dataset import FEATURE_COLUMNS  # noqa: E402

DATA = ROOT / "research/data/processed/training_dataset.parquet"
OUT_MODEL = ROOT / "models/production/xgboost_hq_binary.joblib"
OUT_REG = ROOT / "models/registry/genoguide-xgboost-hq-v1.0.0.json"
OUT_REPORT = ROOT / "docs/model_evaluation.md"
SEED = 62
PATH_LABELS = {"pathogenic", "likely_pathogenic"}
BENIGN_LABELS = {"benign", "likely_benign"}


def metrics_binary(y_true, y_pred, y_score) -> dict:
    prec, rec, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    return {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(prec),
        "recall": float(rec),
        "f1": float(f1),
        "roc_auc": float(roc_auc_score(y_true, y_score)) if len(set(y_true)) > 1 else None,
        "pr_auc": float(average_precision_score(y_true, y_score)) if len(set(y_true)) > 1 else None,
        "confusion_matrix": confusion_matrix(y_true, y_pred).tolist(),
    }


def main() -> int:
    if not DATA.exists():
        print("MISSING", DATA)
        return 2
    df = pd.read_parquet(DATA)
    feats = [c for c in FEATURE_COLUMNS if c in df.columns]
    hq = df[
        df["label"].isin(PATH_LABELS | BENIGN_LABELS)
        & (df["meta_confidence_tier"].fillna(0) >= 2)
    ].copy()
    hq = hq.dropna(subset=["gene"]).reset_index(drop=True)
    hq["y_bin"] = hq["label"].isin(PATH_LABELS).astype(np.int8)
    print(f"HQ rows={len(hq)} class={hq['y_bin'].value_counts().to_dict()} features={len(feats)}")

    split = gene_disjoint_split(hq)
    leak = assert_no_severe_leakage(hq, split)
    print("leakage", leak.get("severity"), "coord_overlap", leak.get("exact_coordinate_overlap"))

    X = hq[feats].to_numpy(dtype=np.float32)
    y = hq["y_bin"].to_numpy()
    tr, va, te = split["train"], split["val"], split["test"]

    model = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("clf", XGBClassifier(
            objective="binary:logistic",
            n_estimators=400,
            max_depth=6,
            learning_rate=0.08,
            subsample=0.9,
            colsample_bytree=0.9,
            tree_method="hist",
            scale_pos_weight=float((y[tr] == 0).sum() / max(1, (y[tr] == 1).sum())),
            random_state=SEED,
            n_jobs=-1,
            eval_metric="aucpr",
        )),
    ])
    model.fit(X[tr], y[tr])
    val_score = model.predict_proba(X[va])[:, 1]
    # threshold from validation (Youden-like: max balanced acc)
    best_t, best_ba = 0.5, -1.0
    for t in np.linspace(0.15, 0.85, 29):
        ba = balanced_accuracy_score(y[va], (val_score >= t).astype(int))
        if ba > best_ba:
            best_ba, best_t = ba, float(t)

    test_score = model.predict_proba(X[te])[:, 1]
    test_pred = (test_score >= best_t).astype(int)
    test_m = metrics_binary(y[te], test_pred, test_score)
    val_m = metrics_binary(y[va], (val_score >= best_t).astype(int), val_score)

    # also report random split (weak baseline, not used for selection)
    rnd = random_split(hq)
    print("gene-disjoint test", test_m)
    print("threshold", best_t, "val_ba", val_m["balanced_accuracy"])

    bundle = {
        "model": model,
        "features": feats,
        "labels": ["benign_spectrum", "pathogenic_spectrum"],
        "task": "binary_pathogenic_spectrum",
        "threshold": best_t,
        "temperature": 1.0,
        "split": split["meta"],
        "leakage": leak,
        "metrics_gene_disjoint_test": test_m,
        "metrics_gene_disjoint_val": val_m,
    }
    OUT_MODEL.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, OUT_MODEL)
    meta = {
        "model_id": "genoguide-xgboost-hq-v1.0.0",
        "registered": datetime.now(timezone.utc).isoformat(),
        "artifact": str(OUT_MODEL.relative_to(ROOT)),
        "training_dataset": {
            "path": str(DATA.relative_to(ROOT)),
            "filter": "label in P/LP/B/LB and meta_confidence_tier>=2",
            "n_hq": int(len(hq)),
        },
        "split": "gene_disjoint",
        "threshold": best_t,
        "metrics_gene_disjoint_test": test_m,
        "leakage": {k: leak.get(k) for k in (
            "severity", "exact_coordinate_overlap", "variation_id_overlap",
            "gene_protein_change_overlap",
        )},
        "seed": SEED,
    }
    OUT_REG.write_text(json.dumps(meta, indent=2))

    five = ROOT / "research/reports/benchmark_results.json"
    five_acc = "see research/reports/benchmark_results.json (5-class ~0.75, not 0.85)"
    if five.exists():
        five_acc = "5-class gene-disjoint accuracy is recorded in benchmark_results.json (~0.75). That is NOT this binary task."

    OUT_REPORT.write_text(
        f"""# Model evaluation (real, held-out)

Generated: {meta['registered']}

## Task (headline)

Binary **pathogenic-spectrum** (P+LP) vs **benign-spectrum** (B+LB) on ClinVar
GRCh38 rows with `meta_confidence_tier >= 2`. VUS and conflicting
interpretations are excluded. Features never include review status or raw
clinical significance.

## Split

Gene-disjoint (seed {SEED}). Leakage audit: **{leak.get('severity')}**.
Exact coordinate overlap: {leak.get('exact_coordinate_overlap')}.
VariationID overlap: {leak.get('variation_id_overlap')}.

n_train={split['meta']['n_train']} n_val={split['meta']['n_val']} n_test={split['meta']['n_test']}

## Held-out TEST (gene-disjoint)

| Metric | Value |
|---|---|
| accuracy | {test_m['accuracy']:.4f} |
| balanced accuracy | {test_m['balanced_accuracy']:.4f} |
| precision | {test_m['precision']:.4f} |
| recall | {test_m['recall']:.4f} |
| F1 | {test_m['f1']:.4f} |
| ROC-AUC | {test_m['roc_auc']:.4f} |
| PR-AUC | {test_m['pr_auc']:.4f} |
| n | {test_m['n']} |
| confusion [[TN,FP],[FN,TP]] | {test_m['confusion_matrix']} |
| decision threshold (from val) | {best_t:.3f} |

Validation (same threshold): accuracy={val_m['accuracy']:.4f} balanced_accuracy={val_m['balanced_accuracy']:.4f}

## 5-class production model (not this artifact)

{five_acc}

Do not report 5-class accuracy as 85% unless that number appears in the 5-class
benchmark file.

## Model

XGBoost binary:logistic, n_estimators=400, max_depth=6, lr=0.08, hist.
Artifact: `{OUT_MODEL.relative_to(ROOT)}`
"""
    )
    print("wrote", OUT_MODEL, OUT_REG, OUT_REPORT)
    print("TEST_ACCURACY", test_m["accuracy"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
