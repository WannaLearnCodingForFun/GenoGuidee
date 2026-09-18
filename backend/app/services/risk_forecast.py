"""Linear (and optional robust) risk forecast. Not a survival or death model."""
from __future__ import annotations

import math
from typing import Any

from .trajectory_score import classify_trend, load_config


def _linreg(xs: list[float], ys: list[float]) -> dict[str, float]:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / syy if syy else 0.0
    dof = max(n - 2, 1)
    mse = ss_res / dof
    se_slope = math.sqrt(mse / sxx) if sxx else 0.0
    return {
        "slope": slope,
        "intercept": intercept,
        "r2": max(0.0, min(1.0, r2)),
        "mse": mse,
        "se_slope": se_slope,
        "n": float(n),
    }


def forecast_risk(scores: list[float], cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    min_n = int(cfg["trend"]["min_snapshots_for_forecast"])
    prefer = int(cfg["trend"]["prefer_forecast"])
    horizon = int(cfg["projection"]["horizon"])
    threshold = float(cfg["projection"]["risk_threshold"])
    unreliable_r2 = float(cfg["projection"]["unreliable_r2"])
    disclaimer = str(cfg.get("disclaimer") or (
        "Projection is based on observed longitudinal genomic trends and is not a "
        "validated mortality prediction."
    )).strip()

    if len(scores) < min_n:
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "message": "Projection unavailable — additional longitudinal observations required.",
            "min_observations": min_n,
            "n_observations": len(scores),
            "disclaimer": disclaimer,
            "mortality_prediction": False,
        }

    xs = [float(i) for i in range(len(scores))]
    fit = _linreg(xs, scores)
    model = "linear_regression"
    if len(scores) >= prefer and fit["r2"] < 0.4:
        # Theil–Sen median slope — more robust on tiny noisy series.
        slopes = []
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                dx = xs[j] - xs[i]
                if dx:
                    slopes.append((scores[j] - scores[i]) / dx)
        if slopes:
            slopes.sort()
            fit["slope"] = slopes[len(slopes) // 2]
            fit["intercept"] = (
                sorted(scores)[len(scores) // 2] - fit["slope"] * xs[len(xs) // 2]
            )
            model = "theil_sen"
    points = []
    last_x = xs[-1]
    for step in range(1, horizon + 1):
        x = last_x + step
        y = fit["intercept"] + fit["slope"] * x
        se = math.sqrt(max(fit["mse"], 1e-6) * (1 + 1 / fit["n"] + ((x - sum(xs) / len(xs)) ** 2) / max(sum((a - sum(xs) / len(xs)) ** 2 for a in xs), 1e-6)))
        lo = max(0.0, y - 1.96 * se)
        hi = min(100.0, y + 1.96 * se)
        points.append({
            "interval": step,
            "score": round(max(0.0, min(100.0, y)), 2),
            "ci_low": round(lo, 2),
            "ci_high": round(hi, 2),
        })

    crossing = None
    current = scores[-1]
    if fit["slope"] > 0.05 and current < threshold:
        remain = (threshold - current) / fit["slope"]
        if remain > 0:
            crossing = round(remain, 1)

    r2 = fit["r2"]
    if r2 < unreliable_r2:
        confidence = "LOW"
        status = "UNRELIABLE"
    elif len(scores) >= prefer and r2 >= 0.5:
        confidence = "HIGH"
        status = "AVAILABLE"
    else:
        confidence = "MODERATE"
        status = "AVAILABLE"

    return {
        "available": status != "UNRELIABLE",
        "status": status,
        "model": model,
        "n_observations": len(scores),
        "current_score": round(current, 2),
        "risk_threshold": threshold,
        "forecast": points,
        "slope": round(fit["slope"], 4),
        "r2": round(r2, 4),
        "trend": classify_trend(scores + [points[0]["score"]], cfg) if points else classify_trend(scores, cfg),
        "threshold_crossing_intervals": crossing,
        "confidence": confidence,
        "horizon": horizon,
        "disclaimer": disclaimer,
        "mortality_prediction": False,
        "message": (
            None if status == "AVAILABLE"
            else "Projection unreliable — trend fit is too weak for this series."
        ),
    }


def linear_slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    xs = [float(i) for i in range(len(values))]
    return round(_linreg(xs, values)["slope"], 6)
