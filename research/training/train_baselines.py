"""
Baseline model training & benchmarking on the real ClinVar-derived dataset.

For every requested split strategy:
    build split → leakage audit (fails on SEVERE) → train each model →
    evaluate on val/test (multiclass + binary pathogenic-spectrum) →
    temperature-scale on val → expert-panel holdout eval → uncertainty/OOD.

Model selection (section 52): primary macro AUPRC on the gene-disjoint test
set, tie-broken by MCC then AUROC, with ECE reported as a safety metric.
Accuracy alone is never used.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import yaml

from research.evaluation import leakage, metrics as M, splits as S
from research.preprocessing.build_training_dataset import FEATURE_COLUMNS, LABELS
from research.training import hardware
from research.training.calibration import TemperatureScaler
from research.training.registry import (
    MODEL_STORE, dataset_fingerprint, record_experiment, register_model)
from research.training.uncertainty import MahalanobisOOD, entropy, max_probability

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "research/reports"

PATH_SPECTRUM = [LABELS.index("pathogenic"), LABELS.index("likely_pathogenic")]
BENIGN_SPECTRUM = [LABELS.index("benign"), LABELS.index("likely_benign")]


def load_config(path: str | Path) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f)


def make_model(name: str, cfg: dict[str, Any], seed: int, n_classes: int):
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    if name == "logreg":
        from sklearn.linear_model import LogisticRegression
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=cfg["logreg"]["max_iter"],
                                       C=cfg["logreg"]["C"],
                                       class_weight="balanced", random_state=seed)),
        ])
    if name == "random_forest":
        from sklearn.ensemble import RandomForestClassifier
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("clf", RandomForestClassifier(
                n_estimators=cfg["random_forest"]["n_estimators"],
                max_depth=cfg["random_forest"]["max_depth"],
                class_weight="balanced_subsample", n_jobs=-1, random_state=seed)),
        ])
    if name == "xgboost":
        from xgboost import XGBClassifier
        c = cfg["xgboost"]
        return XGBClassifier(objective="multi:softprob", num_class=n_classes,
                             n_estimators=c["n_estimators"], max_depth=c["max_depth"],
                             learning_rate=c["learning_rate"], tree_method=c["tree_method"],
                             random_state=seed, n_jobs=-1, verbosity=0)
    if name == "lightgbm":
        from lightgbm import LGBMClassifier
        c = cfg["lightgbm"]
        return LGBMClassifier(n_estimators=c["n_estimators"], num_leaves=c["num_leaves"],
                              learning_rate=c["learning_rate"], class_weight="balanced",
                              random_state=seed, n_jobs=-1, verbosity=-1)
    if name == "mlp":
        from sklearn.neural_network import MLPClassifier
        c = cfg["mlp"]
        return Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", MLPClassifier(hidden_layer_sizes=tuple(c["hidden"]),
                                  max_iter=c["max_iter"], early_stopping=True,
                                  random_state=seed)),
        ])
    raise KeyError(name)


def _sample_weights(y: np.ndarray) -> np.ndarray:
    counts = np.bincount(y, minlength=len(LABELS)).astype(float)
    counts[counts == 0] = 1.0
    w = len(y) / (len(np.unique(y)) * counts)
    return w[y]


def _stratified_cap(idx: np.ndarray, y: np.ndarray, cap: int, seed: int) -> np.ndarray:
    if len(idx) <= cap:
        return idx
    rng = np.random.default_rng(seed)
    frac = cap / len(idx)
    keep = []
    for cls in np.unique(y[idx]):
        cls_idx = idx[y[idx] == cls]
        n = max(int(round(len(cls_idx) * frac)), min(len(cls_idx), 50))
        keep.append(rng.choice(cls_idx, size=min(n, len(cls_idx)), replace=False))
    return np.concatenate(keep)


def binary_eval(y_true_mc: np.ndarray, proba: np.ndarray) -> dict[str, Any]:
    """Pathogenic-spectrum vs benign-spectrum on non-VUS rows."""
    score = proba[:, PATH_SPECTRUM].sum(axis=1)
    is_path = np.isin(y_true_mc, PATH_SPECTRUM)
    is_ben = np.isin(y_true_mc, BENIGN_SPECTRUM)
    mask = is_path | is_ben
    if mask.sum() == 0:
        return {"note": "no non-VUS rows"}
    return M.binary_metrics(is_path[mask].astype(int), score[mask])


def run(config_path: str | Path = "configs/model.yaml",
        models: list[str] | None = None,
        split_names: list[str] | None = None) -> dict[str, Any]:
    cfg = load_config(config_path)
    seed = int(cfg["seed"])
    np.random.seed(seed)
    hw = hardware.detect()

    df = pd.read_parquet(REPO / cfg["dataset"])
    X_all = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y_all = df["y"].to_numpy()

    models = models or cfg["models"]
    split_names = split_names or cfg["splits"]

    all_results: dict[str, Any] = {}
    split_objs: dict[str, dict] = {}
    for sname in split_names:
        split_objs[sname] = S.SPLITTERS[sname](df)
    leak_report = leakage.run_audit(df, split_objs)

    for sname, split in split_objs.items():
        leakage.assert_no_severe_leakage(df, split)
        tr = _stratified_cap(split["train"], y_all, int(cfg["train_sample_cap"]), seed)
        va = _stratified_cap(split["val"], y_all, int(cfg["eval_sample_cap"]), seed)
        te = _stratified_cap(split["test"], y_all, int(cfg["eval_sample_cap"]), seed)
        expert_te = S.expert_holdout(df, {"test": te})

        ood = MahalanobisOOD().fit(X_all[tr])
        ood_states = ood.state(X_all[te])
        split_res: dict[str, Any] = {
            "meta": split["meta"],
            "sampled": {"train": len(tr), "val": len(va), "test": len(te),
                        "expert_holdout": len(expert_te)},
            "leakage": leak_report["splits"][sname],
            "ood_test_distribution": {s: ood_states.count(s) for s in set(ood_states)},
            "models": {},
        }

        probas_test: dict[str, np.ndarray] = {}
        for mname in models:
            t0 = time.time()
            model = make_model(mname, cfg, seed, n_classes=len(LABELS))
            fit_kwargs = {}
            if mname == "xgboost":
                fit_kwargs["sample_weight"] = _sample_weights(y_all[tr])
            model.fit(X_all[tr], y_all[tr], **fit_kwargs)
            runtime = time.time() - t0

            proba_va = model.predict_proba(X_all[va])
            proba_te = model.predict_proba(X_all[te])
            scaler = TemperatureScaler().fit(proba_va, y_all[va])
            proba_te_cal = scaler.transform(proba_te)
            probas_test[mname] = proba_te_cal

            entry = {
                "runtime_sec": round(runtime, 1),
                "temperature": round(scaler.temperature, 3),
                "val": M.multiclass_metrics(y_all[va], proba_va, LABELS),
                "test": M.multiclass_metrics(y_all[te], proba_te, LABELS),
                "test_calibrated": M.multiclass_metrics(y_all[te], proba_te_cal, LABELS),
                "test_binary_path_spectrum": binary_eval(y_all[te], proba_te_cal),
                "uncertainty": {
                    "mean_entropy": float(entropy(proba_te_cal).mean()),
                    "mean_max_prob": float(max_probability(proba_te_cal).mean()),
                },
            }
            if len(expert_te):
                entry["expert_holdout"] = M.multiclass_metrics(
                    y_all[expert_te], scaler.transform(model.predict_proba(X_all[expert_te])), LABELS)
            split_res["models"][mname] = entry

            if sname == cfg["selection_policy"]["headline_split"]:
                MODEL_STORE.mkdir(parents=True, exist_ok=True)
                joblib.dump({"model": model, "temperature": scaler.temperature,
                             "features": FEATURE_COLUMNS, "labels": LABELS,
                             "ood": ood},
                            MODEL_STORE / f"{mname}_gene_disjoint.joblib")

        if len(probas_test) >= 2:
            from research.training.uncertainty import ensemble_variance
            split_res["ensemble_variance_mean"] = float(
                ensemble_variance(list(probas_test.values())).mean())
        all_results[sname] = split_res

    # ---- model selection ----------------------------------------------------
    pol = cfg["selection_policy"]
    head = all_results.get(pol["headline_split"], next(iter(all_results.values())))
    ranking = sorted(
        head["models"].items(),
        key=lambda kv: (
            -(kv[1]["test_calibrated"].get("macro_auprc_ovr") or 0),
            -(kv[1]["test_calibrated"].get("mcc") or 0),
            -(kv[1]["test_calibrated"].get("macro_auroc_ovr") or 0),
        ),
    )
    best_name = ranking[0][0]
    best = ranking[0][1]

    exp_id = record_experiment({
        "task": "clinvar_5class_baselines",
        "config": cfg, "hardware": hw,
        "dataset": dataset_fingerprint(REPO / cfg["dataset"]),
        "splits": {k: v["meta"] for k, v in split_objs.items()},
        "results": all_results,
        "selection": {"policy": pol, "best_model": best_name,
                      "ranking": [r[0] for r in ranking]},
    })

    artifact = MODEL_STORE / f"{best_name}_gene_disjoint.joblib"
    model_id = f"genoguide-tabular-{best_name}-v0.1.0"
    register_model(model_id, artifact if artifact.exists() else None, {
        "experiment_id": exp_id,
        "training_dataset": dataset_fingerprint(REPO / cfg["dataset"]),
        "feature_schema": FEATURE_COLUMNS,
        "labels": LABELS,
        "hyperparameters": cfg.get(best_name if best_name != "random_forest" else "random_forest"),
        "metrics_gene_disjoint_test": {
            k: best["test_calibrated"].get(k)
            for k in ("macro_auprc_ovr", "macro_auroc_ovr", "mcc", "ece",
                      "balanced_accuracy", "macro_f1")},
        "binary_path_spectrum": best.get("test_binary_path_spectrum"),
        "calibration": {"method": "temperature", "T": best["temperature"]},
        "seed": seed,
    })

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "benchmark_results.json").write_text(
        json.dumps({"experiment_id": exp_id, "results": all_results,
                    "best_model": best_name}, indent=2, default=str))
    _write_benchmark_table(all_results, best_name)
    return {"experiment_id": exp_id, "best_model": best_name,
            "model_id": model_id, "results": all_results}


def _write_benchmark_table(results: dict[str, Any], best: str) -> None:
    lines = ["# GenoGuide benchmark table (real ClinVar data)", ""]
    for sname, sres in results.items():
        lines += [f"## split: {sname}",
                  f"(train={sres['sampled']['train']:,} test={sres['sampled']['test']:,} "
                  f"leakage={sres['leakage']['severity']})", "",
                  "| model | AUPRC(macro) | AUROC(macro) | MCC | bal.acc | macro F1 | ECE(cal) | binary AUROC | binary AUPRC |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for m, r in sres["models"].items():
            tc, tb = r["test_calibrated"], r.get("test_binary_path_spectrum", {})
            def f(x): return f"{x:.3f}" if isinstance(x, float) else "—"
            star = " **⭐**" if m == best and sname == "gene_disjoint" else ""
            lines.append(
                f"| {m}{star} | {f(tc.get('macro_auprc_ovr'))} | {f(tc.get('macro_auroc_ovr'))} "
                f"| {f(tc.get('mcc'))} | {f(tc.get('balanced_accuracy'))} | {f(tc.get('macro_f1'))} "
                f"| {f(tc.get('ece'))} | {f(tb.get('auroc'))} | {f(tb.get('auprc'))} |")
        lines.append("")
    (REPORTS / "benchmark_table.md").write_text("\n".join(lines))


if __name__ == "__main__":
    out = run()
    print(json.dumps({"experiment": out["experiment_id"], "best": out["best_model"]}, indent=2))
