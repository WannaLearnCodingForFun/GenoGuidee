#!/usr/bin/env python3
"""Re-evaluate saved HQ binary and production 5-class artifacts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    hq = ROOT / "models/registry/genoguide-xgboost-hq-v1.0.0.json"
    if hq.exists():
        print("HQ binary", json.dumps(json.loads(hq.read_text())["metrics_gene_disjoint_test"], indent=2))
    else:
        print("HQ registry missing — run scripts/train_variant_model.py")
    xgb = ROOT / "models/production/xgboost_gene_disjoint.joblib"
    if xgb.exists():
        b = joblib.load(xgb)
        print("5-class xgb loaded", "features", len(b.get("features") or []), "labels", b.get("labels"))
    logreg = ROOT / "models/registry/genoguide-tabular-logreg-v0.1.0.json"
    if logreg.exists():
        print("logreg 5-class", json.dumps(json.loads(logreg.read_text()).get("metrics_gene_disjoint_test"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
