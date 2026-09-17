"""Reproduce the existing GenoGuide demo: BRCA1, TP53, CFTR, ACMG, ML, KG, provenance."""
from __future__ import annotations

from rich.console import Console

console = Console()

SHOWCASE = ["VAR-BRCA1-5266DUP", "VAR-TP53-R158H", "VAR-CFTR-F508DEL"]


def run() -> int:
    from fastapi.testclient import TestClient

    from app.acmg import classify
    from app.dataset import PATIENTS, VARIANTS_BY_ID
    from app.main import app
    from app.ml import esm_representation, predict

    failed = []
    with TestClient(app) as client:
        health = client.get("/health")
        if health.status_code != 200:
            failed.append("health")
        for vid in SHOWCASE:
            v = VARIANTS_BY_ID[vid]
            r = client.post("/api/analyze", json={"variant_id": vid, "patient_id": "G-1027"})
            if r.status_code != 200:
                failed.append(vid)
                continue
            body = r.json()
            acmg = classify(v)
            if body["acmg"]["classification"] != acmg["classification"]:
                failed.append(f"{vid}:acmg")
            if body["reconciliation"]["final_classification"] != acmg["classification"]:
                failed.append(f"{vid}:override")
            esm = esm_representation(v)
            ml = predict(v, esm["delta_score"])
            if not ml.get("top_class"):
                failed.append(f"{vid}:ml")
        g = client.get("/api/graph/G-1027")
        if g.status_code != 200:
            failed.append("knowledge-graph")
        p = client.get("/api/provenance/audit")
        if p.status_code != 200:
            failed.append("provenance")
        ctx = client.get("/api/patients/G-1027/context")
        if ctx.status_code != 200:
            failed.append("patient-context")
        if PATIENTS[0]["id"] != "G-1027":
            failed.append("synthetic-patient")
    if failed:
        console.print(f"[red]demo-regression FAIL[/red] {failed}")
        return 1
    console.print("[green]demo-regression PASS[/green] BRCA1 / TP53 / CFTR / patient context / ACMG / ML / KG / provenance")
    return 0
