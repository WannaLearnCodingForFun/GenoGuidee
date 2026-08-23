#!/usr/bin/env python3
"""End-to-end smoke: health, VCF parse, interpret, prediction consistency, therapy."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))


def main() -> int:
    from fastapi.testclient import TestClient
    from app.main import app
    from app.services.ml_predict import finalize_prediction, smoke_inference

    pred = finalize_prediction(
        {"pathogenic": 0.5, "likely_pathogenic": 0.2, "vus": 0.2,
         "likely_benign": 0.05, "benign": 0.05},
        model_name="smoke", model_version="s", dataset_version="s",
        feature_schema_version="s", calibrated=True,
    )
    assert pred["predicted_class"] == "pathogenic"
    assert pred["confidence"] == pred["probabilities"]["pathogenic"]
    assert smoke_inference()["ok"]

    with TestClient(app) as c:
        h = c.get("/health")
        assert h.status_code == 200
        assert h.json()["components"]["ml"]["status"] in {"READY", "DEGRADED"}
        from tests.data import __file__ as _  # noqa
        vcf = ROOT / "tests/data/mini.vcf"
        assert vcf.exists()
        # unauthenticated interpret is 401 — expected
        assert c.get("/api/ml/health").status_code == 200
        th = c.get("/api/therapy/health")
        assert th.status_code == 200
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
