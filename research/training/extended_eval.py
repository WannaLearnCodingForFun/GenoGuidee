"""
Leakage-safe extra evaluation: feature ablations, calibration comparison,
error analysis, optional SHAP on tree artifacts.

Does not invent metrics. Missing optional deps / artifacts are recorded as
NOT RUN. Never uses ClinVar/ACMG labels as features.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from research.evaluation import leakage, metrics as M, splits as S
from research.preprocessing.build_training_dataset import FEATURE_COLUMNS, FORBIDDEN_AS_FEATURES, LABELS
from research.training.calibration import BinaryCalibrator, TemperatureScaler
from research.training.train_baselines import (
    MODEL_STORE, PATH_SPECTRUM, REPO, REPORTS, _sample_weights, _stratified_cap,
    binary_eval, make_model,
)

CORE = [c for c in FEATURE_COLUMNS if c.startswith("csq_") or c.startswith("vt_")
        or c in ("ref_len", "alt_len", "len_delta")]
GENE = ["loeuf", "pli", "mis_z", "syn_z", "gene_feat_missing",
        "clingen_validity", "clingen_n_diseases"]
AM = ["am_pathogenicity", "am_missing"]
POP = ["log10_af", "af_missing", "is_rare"]

ABLATIONS = {
    "tabular_only": CORE,
    "without_alphamissense": [c for c in FEATURE_COLUMNS if c not in AM],
    "without_population": [c for c in FEATURE_COLUMNS if c not in POP],
    "without_gene_features": [c for c in FEATURE_COLUMNS if c not in GENE],
    "all_available": list(FEATURE_COLUMNS),
}


def _present(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns]


def run(*, train_cap: int = 40_000, eval_cap: int = 15_000, seed: int = 62) -> dict[str, Any]:
    parquet = REPO / "research/data/processed/training_dataset.parquet"
    if not parquet.exists():
        raise FileNotFoundError(parquet)
    leaked = sorted(FORBIDDEN_AS_FEATURES & set(FEATURE_COLUMNS))
    if leaked:
        raise RuntimeError(f"label leakage in FEATURE_COLUMNS: {leaked}")

    df = pd.read_parquet(parquet)
    y = df["y"].to_numpy()
    split = S.gene_disjoint_split(df)
    leak = leakage.run_audit(df, {"gene_disjoint": split})
    leakage.assert_no_severe_leakage(df, split)
    tr = _stratified_cap(split["train"], y, train_cap, seed)
    va = _stratified_cap(split["val"], y, eval_cap, seed)
    te = _stratified_cap(split["test"], y, eval_cap, seed)

    cfg = {
        "logreg": {"max_iter": 800, "C": 1.0},
        "xgboost": {"n_estimators": 80, "max_depth": 6, "learning_rate": 0.1, "tree_method": "hist"},
        "random_forest": {"n_estimators": 80, "max_depth": 12},
        "lightgbm": {"n_estimators": 80, "num_leaves": 31, "learning_rate": 0.1},
        "mlp": {"hidden": [32, 16], "max_iter": 20},
    }

    ablation_rows: list[dict[str, Any]] = []
    for name, cols in ABLATIONS.items():
        feats = _present(df, cols)
        if not feats:
            ablation_rows.append({"ablation": name, "status": "NOT RUN — no matching columns"})
            continue
        X = df[feats].to_numpy(dtype=np.float32)
        model = make_model("logreg", cfg, seed, n_classes=len(LABELS))
        model.fit(X[tr], y[tr])
        proba_va = model.predict_proba(X[va])
        proba_te = model.predict_proba(X[te])
        scaler = TemperatureScaler().fit(proba_va, y[va])
        cal = scaler.transform(proba_te)
        met = M.multiclass_metrics(y[te], cal, LABELS)
        ablation_rows.append({
            "ablation": name,
            "n_features": len(feats),
            "features": ",".join(feats),
            "n_train": len(tr),
            "n_test": len(te),
            "macro_auprc": met.get("macro_auprc_ovr"),
            "macro_auroc": met.get("macro_auroc_ovr"),
            "mcc": met.get("mcc"),
            "ece": met.get("ece"),
            "balanced_accuracy": met.get("balanced_accuracy"),
            "macro_f1": met.get("macro_f1"),
            "brier": met.get("brier_multiclass"),
            "status": "RAN",
        })

    extra_models: dict[str, Any] = {}
    feats_all = _present(df, FEATURE_COLUMNS)
    X_all = df[feats_all].to_numpy(dtype=np.float32)
    for mname in ("logreg", "random_forest", "xgboost", "lightgbm", "mlp"):
        try:
            model = make_model(mname, cfg, seed, n_classes=len(LABELS))
            fit_kwargs = {}
            if mname == "xgboost":
                fit_kwargs["sample_weight"] = _sample_weights(y[tr])
            model.fit(X_all[tr], y[tr], **fit_kwargs)
            p_va = model.predict_proba(X_all[va])
            p_te = model.predict_proba(X_all[te])
            T = TemperatureScaler().fit(p_va, y[va])
            p_cal = T.transform(p_te)
            extra_models[mname] = {
                "status": "RAN",
                "temperature": T.temperature,
                "test": M.multiclass_metrics(y[te], p_te, LABELS),
                "test_calibrated": M.multiclass_metrics(y[te], p_cal, LABELS),
                "binary": binary_eval(y[te], p_cal),
                "binary_calibration": _fit_binary_calibrators(y[va], p_va, y[te], p_te),
            }
        except Exception as exc:  # noqa: BLE001 — optional model / missing package
            extra_models[mname] = {"status": f"NOT RUN — {type(exc).__name__}: {exc}"}

    cal_compare = _binary_calibration_compare(y[va], y[te], extra_models)
    shap_report = _shap_tree(df, feats_all, te, y)
    errors = _error_analysis(y[te], extra_models.get("logreg"), LABELS)

    REPORTS.mkdir(parents=True, exist_ok=True)
    _write_csv(REPORTS / "ablation_results.csv", ablation_rows)
    _write_csv(REPORTS / "error_analysis.csv", errors)
    payload = {
        "split": "gene_disjoint",
        "leakage": leak["splits"]["gene_disjoint"],
        "caps": {"train": len(tr), "val": len(va), "test": len(te)},
        "note": "Ablation/extra-model caps are smaller than the 300k/120k production run. "
                "Do not treat these as a production replacement unless AUPRC improves.",
        "forbidden_features_in_model": leaked,
        "ablations": ablation_rows,
        "models": {k: _slim(v) for k, v in extra_models.items()},
        "calibration_binary": cal_compare,
        "shap": shap_report,
        "esm2": "NOT IMPLEMENTED — no protein sequence column in training_dataset.parquet",
        "stacked_ensemble": "NOT IMPLEMENTED — no out-of-fold predictions generated",
    }
    (REPORTS / "extended_eval.json").write_text(json.dumps(payload, indent=2, default=str))
    return payload


def _slim(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("status") != "RAN":
        return entry
    tc = entry["test_calibrated"]
    return {
        "status": "RAN",
        "temperature": entry["temperature"],
        "macro_auprc": tc.get("macro_auprc_ovr"),
        "macro_auroc": tc.get("macro_auroc_ovr"),
        "mcc": tc.get("mcc"),
        "ece": tc.get("ece"),
        "balanced_accuracy": tc.get("balanced_accuracy"),
        "macro_f1": tc.get("macro_f1"),
        "brier": tc.get("brier_multiclass"),
        "uncalibrated_ece": entry["test"].get("ece"),
        "binary_auprc": (entry.get("binary") or {}).get("auprc"),
        "binary_auroc": (entry.get("binary") or {}).get("auroc"),
        "binary_calibration": entry.get("binary_calibration"),
    }


def _path_score(proba: np.ndarray) -> np.ndarray:
    return proba[:, PATH_SPECTRUM].sum(axis=1)


def _fit_binary_calibrators(y_va: np.ndarray, p_va: np.ndarray,
                            y_te: np.ndarray, p_te: np.ndarray) -> dict[str, Any]:
    is_path_va = np.isin(y_va, PATH_SPECTRUM)
    is_ben_va = np.isin(y_va, [LABELS.index("benign"), LABELS.index("likely_benign")])
    is_path_te = np.isin(y_te, PATH_SPECTRUM)
    is_ben_te = np.isin(y_te, [LABELS.index("benign"), LABELS.index("likely_benign")])
    m_va, m_te = is_path_va | is_ben_va, is_path_te | is_ben_te
    if m_va.sum() < 50 or m_te.sum() < 50:
        return {"status": "NOT RUN — too few non-VUS rows"}
    score_va, score_te = _path_score(p_va)[m_va], _path_score(p_te)[m_te]
    yb_va, yb_te = is_path_va[m_va].astype(int), is_path_te[m_te].astype(int)
    out: dict[str, Any] = {"uncalibrated_brier": float(
        ((score_te - yb_te) ** 2).mean())}
    for method in ("platt", "isotonic"):
        cal = BinaryCalibrator(method="isotonic" if method == "isotonic" else "platt")
        try:
            pred = cal.fit(score_va, yb_va).transform(score_te)
            out[method] = {
                "brier": float(((pred - yb_te) ** 2).mean()),
                "auprc": float(M.binary_metrics(yb_te, pred).get("auprc", float("nan"))),
            }
        except Exception as exc:  # noqa: BLE001
            out[method] = {"status": f"NOT RUN — {type(exc).__name__}: {exc}"}
    return out


def _binary_calibration_compare(_y_va: np.ndarray, _y_te: np.ndarray,
                                models: dict[str, Any]) -> dict[str, Any]:
    logreg = models.get("logreg")
    if not logreg or logreg.get("status") != "RAN":
        return {"status": "NOT RUN — logreg unavailable"}
    return logreg.get("binary_calibration") or {"status": "NOT RUN"}


def _shap_tree(df: pd.DataFrame, feats: list[str], te: np.ndarray,
               y: np.ndarray) -> dict[str, Any]:
    artifact = MODEL_STORE / "xgboost_gene_disjoint.joblib"
    if not artifact.exists():
        return {"status": "NOT RUN — models/production/xgboost_gene_disjoint.joblib missing"}
    try:
        import shap  # type: ignore
        import joblib
    except Exception as exc:  # noqa: BLE001
        return {"status": f"NOT RUN — {type(exc).__name__}: {exc}"}
    try:
        bundle = joblib.load(artifact)
        model = bundle["model"]
        use = [c for c in bundle.get("features", feats) if c in df.columns]
        rng = np.random.default_rng(62)
        sample = rng.choice(te, size=min(400, len(te)), replace=False)
        X = df.iloc[sample][use].to_numpy(dtype=np.float32)
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(X)
        if isinstance(sv, list):
            mag = np.mean([np.abs(a).mean(axis=0) for a in sv], axis=0)
        else:
            mag = np.abs(sv).mean(axis=0)
            if mag.ndim > 1:
                mag = mag.mean(axis=-1)
        ranked = sorted(zip(use, mag.tolist()), key=lambda t: -t[1])[:15]
        return {"status": "RAN", "n": int(len(sample)), "top_mean_abs_shap": ranked}
    except Exception as exc:  # noqa: BLE001
        return {"status": f"NOT RUN — {type(exc).__name__}: {exc}"}


def _error_analysis(y_te: np.ndarray, logreg_entry: dict[str, Any] | None,
                    labels: list[str]) -> list[dict[str, Any]]:
    rows = []
    if not logreg_entry or logreg_entry.get("status") != "RAN":
        return [{"status": "NOT RUN — logreg metrics missing"}]
    cm = (logreg_entry.get("test_calibrated") or {}).get("confusion_matrix")
    if not cm:
        return [{"status": "NOT RUN — confusion matrix missing"}]
    for i, lab in enumerate(labels):
        row = cm[i]
        n = int(sum(row))
        correct = int(row[i]) if i < len(row) else 0
        rows.append({
            "true_class": lab,
            "n_test": n,
            "correct": correct,
            "recall": (correct / n) if n else None,
            "confused_as": ",".join(
                f"{labels[j]}:{row[j]}" for j in range(len(row)) if j != i and row[j]
            ),
        })
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    out = run()
    print(json.dumps({"ablations": len(out["ablations"]),
                      "models": {k: v.get("status") for k, v in out["models"].items()},
                      "shap": out["shap"].get("status")}, indent=2))
