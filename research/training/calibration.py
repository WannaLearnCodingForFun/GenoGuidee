"""
Probability calibration (section 29).

Temperature scaling for multiclass probability matrices (fit on validation,
never on test) and isotonic/Platt for binary scores via scikit-learn.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

_EPS = 1e-12


class TemperatureScaler:
    """Multiclass temperature scaling on log-probabilities."""

    def __init__(self) -> None:
        self.temperature: float = 1.0

    def fit(self, proba_val: np.ndarray, y_val: np.ndarray) -> "TemperatureScaler":
        logp = np.log(np.clip(proba_val, _EPS, 1.0))

        def nll(t: float) -> float:
            z = logp / t
            z -= z.max(axis=1, keepdims=True)
            p = np.exp(z)
            p /= p.sum(axis=1, keepdims=True)
            return -np.mean(np.log(np.clip(p[np.arange(len(y_val)), y_val], _EPS, 1.0)))

        res = minimize_scalar(nll, bounds=(0.05, 20.0), method="bounded")
        self.temperature = float(res.x)
        return self

    def transform(self, proba: np.ndarray) -> np.ndarray:
        z = np.log(np.clip(proba, _EPS, 1.0)) / self.temperature
        z -= z.max(axis=1, keepdims=True)
        p = np.exp(z)
        return p / p.sum(axis=1, keepdims=True)


class BinaryCalibrator:
    """Isotonic (default) or Platt calibration for a binary score."""

    def __init__(self, method: str = "isotonic") -> None:
        self.method = method
        self._iso: IsotonicRegression | None = None
        self._platt: LogisticRegression | None = None

    def fit(self, score_val: np.ndarray, y_val: np.ndarray) -> "BinaryCalibrator":
        if self.method == "isotonic":
            self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self._iso.fit(score_val, y_val)
        else:
            self._platt = LogisticRegression(C=1e6)
            self._platt.fit(score_val.reshape(-1, 1), y_val)
        return self

    def transform(self, score: np.ndarray) -> np.ndarray:
        if self._iso is not None:
            return self._iso.predict(score)
        assert self._platt is not None
        return self._platt.predict_proba(score.reshape(-1, 1))[:, 1]
