"""
Evaluation metric suite (sections 48–49).

Multiclass: accuracy, balanced accuracy, macro/weighted F1, MCC,
one-vs-rest AUROC (macro), macro AUPRC, Brier (multiclass), ECE,
per-class precision/recall/specificity, confusion matrix.

Clinical prioritization (binary pathogenic-spectrum score):
precision@k, recall@k, recall at fixed FPR.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score, average_precision_score, balanced_accuracy_score,
    brier_score_loss, confusion_matrix, f1_score, matthews_corrcoef,
    precision_score, recall_score, roc_auc_score, roc_curve,
)


def expected_calibration_error(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 15) -> float:
    """Top-label ECE."""
    conf = proba.max(axis=1)
    pred = proba.argmax(axis=1)
    correct = (pred == y_true).astype(float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.sum() == 0:
            continue
        ece += mask.mean() * abs(correct[mask].mean() - conf[mask].mean())
    return float(ece)


def multiclass_brier(y_true: np.ndarray, proba: np.ndarray) -> float:
    onehot = np.zeros_like(proba)
    onehot[np.arange(len(y_true)), y_true] = 1.0
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


def reliability_table(y_true: np.ndarray, proba: np.ndarray, n_bins: int = 10) -> list[dict]:
    conf = proba.max(axis=1)
    pred = proba.argmax(axis=1)
    correct = (pred == y_true).astype(float)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    table = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (conf > lo) & (conf <= hi)
        if mask.sum():
            table.append({"bin": f"({lo:.1f},{hi:.1f}]", "n": int(mask.sum()),
                          "mean_confidence": float(conf[mask].mean()),
                          "empirical_accuracy": float(correct[mask].mean())})
    return table


def multiclass_metrics(y_true: np.ndarray, proba: np.ndarray,
                       labels: list[str]) -> dict[str, Any]:
    y_pred = proba.argmax(axis=1)
    present = np.unique(y_true)
    metrics: dict[str, Any] = {
        "n": int(len(y_true)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "mcc": float(matthews_corrcoef(y_true, y_pred)),
        "brier_multiclass": multiclass_brier(y_true, proba),
        "ece": expected_calibration_error(y_true, proba),
        "confusion_matrix": confusion_matrix(y_true, y_pred,
                                             labels=list(range(len(labels)))).tolist(),
        "labels": labels,
    }
    try:
        metrics["macro_auroc_ovr"] = float(roc_auc_score(
            y_true, proba[:, present] if len(present) < len(labels) else proba,
            multi_class="ovr", average="macro",
            labels=present if len(present) < len(labels) else None))
    except ValueError:
        metrics["macro_auroc_ovr"] = None
    # macro AUPRC (one-vs-rest)
    auprcs = []
    for k in present:
        yk = (y_true == k).astype(int)
        if yk.sum() and (1 - yk).sum():
            auprcs.append(average_precision_score(yk, proba[:, k]))
    metrics["macro_auprc_ovr"] = float(np.mean(auprcs)) if auprcs else None

    per_class = {}
    cm = np.array(metrics["confusion_matrix"])
    for i, name in enumerate(labels):
        tp = cm[i, i]; fn = cm[i].sum() - tp
        fp = cm[:, i].sum() - tp; tn = cm.sum() - tp - fn - fp
        per_class[name] = {
            "support": int(cm[i].sum()),
            "precision": float(tp / (tp + fp)) if tp + fp else None,
            "recall_sensitivity": float(tp / (tp + fn)) if tp + fn else None,
            "specificity": float(tn / (tn + fp)) if tn + fp else None,
        }
    metrics["per_class"] = per_class
    metrics["reliability"] = reliability_table(y_true, proba)
    return metrics


def binary_metrics(y_true: np.ndarray, score: np.ndarray) -> dict[str, Any]:
    out: dict[str, Any] = {"n": int(len(y_true)), "prevalence": float(np.mean(y_true))}
    if len(np.unique(y_true)) < 2:
        out["note"] = "single class present; discrimination metrics undefined"
        return out
    out["auroc"] = float(roc_auc_score(y_true, score))
    out["auprc"] = float(average_precision_score(y_true, score))
    out["brier"] = float(brier_score_loss(y_true, np.clip(score, 0, 1)))
    pred = (score >= 0.5).astype(int)
    out["mcc"] = float(matthews_corrcoef(y_true, pred))
    out["precision_at_0.5"] = float(precision_score(y_true, pred, zero_division=0))
    out["recall_at_0.5"] = float(recall_score(y_true, pred, zero_division=0))

    order = np.argsort(-score)
    for k in (10, 50, 200):
        if len(y_true) >= k:
            topk = y_true[order[:k]]
            out[f"precision_at_{k}"] = float(topk.mean())
            out[f"recall_at_{k}"] = float(topk.sum() / max(y_true.sum(), 1))
    fpr, tpr, _ = roc_curve(y_true, score)
    for target in (0.01, 0.05):
        mask = fpr <= target
        out[f"recall_at_fpr_{target}"] = float(tpr[mask].max()) if mask.any() else 0.0
    return out
