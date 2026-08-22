"""
Experiment tracking + model registry (sections 46–47).

Lightweight JSON registries — no external services required.
    research/experiments/<experiment_id>.json   one file per training run
    models/registry/<model_id>.json             metadata for every saved model
    models/production/                          binary artifacts (git-ignored)
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
EXPERIMENTS = REPO / "research/experiments"
MODEL_REGISTRY = REPO / "models/registry"
MODEL_STORE = REPO / "models/production"


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def dataset_fingerprint(parquet_path: Path) -> dict[str, Any]:
    st = parquet_path.stat()
    return {"path": str(parquet_path.relative_to(REPO)),
            "size_bytes": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()}


def record_experiment(payload: dict[str, Any]) -> str:
    EXPERIMENTS.mkdir(parents=True, exist_ok=True)
    exp_id = f"exp-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    payload = {"experiment_id": exp_id,
               "recorded": datetime.now(timezone.utc).isoformat(),
               "git_commit": git_commit(), **payload}
    (EXPERIMENTS / f"{exp_id}.json").write_text(json.dumps(payload, indent=2, default=str))
    return exp_id


def register_model(model_id: str, artifact_path: Path | None, meta: dict[str, Any]) -> dict[str, Any]:
    MODEL_REGISTRY.mkdir(parents=True, exist_ok=True)
    checksum = None
    if artifact_path and artifact_path.exists():
        h = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        checksum = h.hexdigest()
    entry = {
        "model_id": model_id,
        "registered": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "artifact": str(artifact_path.relative_to(REPO)) if artifact_path else None,
        "artifact_sha256": checksum,
        **meta,
    }
    (MODEL_REGISTRY / f"{model_id}.json").write_text(json.dumps(entry, indent=2, default=str))
    return entry
