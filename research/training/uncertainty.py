"""
Uncertainty & out-of-distribution detection (sections 30–31).

Per-sample uncertainty:
    entropy, max_probability, (ensemble variance when ≥2 models available)

OOD detector: Mahalanobis distance in standardized feature space, fit on the
TRAINING distribution only. Thresholds are set from training-set quantiles
(q95 → LOW_CONFIDENCE, q999 → OUT_OF_DISTRIBUTION); nothing is tuned on test.
"""
from __future__ import annotations

from typing import Any

import numpy as np

_EPS = 1e-12


def entropy(proba: np.ndarray) -> np.ndarray:
    p = np.clip(proba, _EPS, 1.0)
    return -np.sum(p * np.log(p), axis=1)


def max_probability(proba: np.ndarray) -> np.ndarray:
    return proba.max(axis=1)


def ensemble_variance(probas: list[np.ndarray]) -> np.ndarray:
    """Mean over classes of the across-model variance of predicted probability."""
    stack = np.stack(probas)               # (models, n, classes)
    return stack.var(axis=0).mean(axis=1)


class MahalanobisOOD:
    def __init__(self) -> None:
        self.mean_: np.ndarray | None = None
        self.inv_cov_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None
        self.q95_: float | None = None
        self.q999_: float | None = None

    def fit(self, X_train: np.ndarray) -> "MahalanobisOOD":
        X = np.asarray(X_train, dtype=float)
        X = np.nan_to_num(X, nan=0.0)
        self.mean_ = X.mean(axis=0)
        self.scale_ = X.std(axis=0)
        self.scale_[self.scale_ < _EPS] = 1.0
        Z = (X - self.mean_) / self.scale_
        cov = np.cov(Z, rowvar=False) + np.eye(Z.shape[1]) * 1e-3
        self.inv_cov_ = np.linalg.pinv(cov)
        d = self.distance(X_train)
        self.q95_ = float(np.quantile(d, 0.95))
        self.q999_ = float(np.quantile(d, 0.999))
        return self

    def distance(self, X: np.ndarray) -> np.ndarray:
        assert self.mean_ is not None
        X = np.nan_to_num(np.asarray(X, dtype=float), nan=0.0)
        Z = (X - self.mean_) / self.scale_
        centered = Z  # mean already removed via standardization against train mean
        return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", centered, self.inv_cov_, centered), 0.0))

    def state(self, X: np.ndarray) -> list[str]:
        d = self.distance(X)
        out = np.full(len(d), "IN_DISTRIBUTION", dtype=object)
        out[d > self.q95_] = "LOW_CONFIDENCE"
        out[d > self.q999_] = "OUT_OF_DISTRIBUTION"
        return out.tolist()

    def to_dict(self) -> dict[str, Any]:
        return {"q95": self.q95_, "q999": self.q999_,
                "n_features": None if self.mean_ is None else int(len(self.mean_))}


def summarize(proba: np.ndarray, probas_all_models: list[np.ndarray] | None = None) -> dict[str, Any]:
    s: dict[str, Any] = {
        "mean_entropy": float(entropy(proba).mean()),
        "mean_max_probability": float(max_probability(proba).mean()),
    }
    if probas_all_models and len(probas_all_models) >= 2:
        s["mean_ensemble_variance"] = float(ensemble_variance(probas_all_models).mean())
    return s
