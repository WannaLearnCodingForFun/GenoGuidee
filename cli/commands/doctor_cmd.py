"""System doctor: database, models, ACMG, KG, provenance, API, auth, migrations."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def run() -> int:
    rows: list[tuple[str, str, str]] = []
    ok = True

    def add(name: str, status: str, detail: str) -> None:
        nonlocal ok
        if status not in {"PASS", "READY", "OPTIONAL"}:
            ok = False
        rows.append((name, status, detail))

    try:
        from app import clinical_db as DB
        DB.init()
        integ = DB.integrity_report()
        add("database", "PASS", f"clinical.db integrity={integ}")
        con = DB.connect()
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        finally:
            con.close()
        needed = {"interpretation_versions", "evidence_graph_edges", "watchlist", "reanalysis_jobs"}
        missing = needed - tables
        add("migrations", "PASS" if not missing else "FAIL",
            "platform tables present" if not missing else f"missing {sorted(missing)}")
    except Exception as exc:
        add("database", "FAIL", str(exc))
        add("migrations", "FAIL", str(exc))

    try:
        from app.services.ml_predict import load_production_bundle, smoke_inference
        bundle = load_production_bundle()
        smoke = smoke_inference()
        add("models", "PASS" if bundle and smoke.get("ok") else "FAIL",
            (bundle or {}).get("meta", {}).get("model_id", "no bundle") if bundle else "no model")
    except Exception as exc:
        add("models", "FAIL", str(exc))

    try:
        from app.interpretation.acmg_v2 import EvidenceInputs, evaluate
        r = evaluate(EvidenceInputs())
        add("ACMG", "PASS" if r.classification == "VUS" else "FAIL",
            f"empty inputs → {r.classification}")
    except Exception as exc:
        add("ACMG", "FAIL", str(exc))

    try:
        from app.knowledge_graph.graph import KG_VERSION
        from app.platform.evidence_graph import KG_VERSION as KG2
        add("knowledge_graph", "PASS", f"{KG_VERSION} + {KG2}")
    except Exception as exc:
        add("knowledge_graph", "FAIL", str(exc))

    try:
        from app.provenance2 import ledger
        chain = ledger.verify_chain()
        add("provenance", "PASS" if chain.get("valid") else "FAIL", f"blocks={chain.get('blocks')}")
    except Exception as exc:
        add("provenance", "FAIL", str(exc))

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        with TestClient(app) as c:
            h = c.get("/health")
            v1 = c.get("/api/v1/health")
            add("API", "PASS" if h.status_code == 200 and v1.status_code == 200 else "FAIL",
                f"/health={h.status_code} /api/v1/health={v1.status_code}")
    except Exception as exc:
        add("API", "FAIL", str(exc))

    try:
        from app.local_auth import hash_password, verify_password
        stored = hash_password("doctor-check")
        add("authentication", "PASS" if verify_password("doctor-check", stored) else "FAIL",
            "pbkdf2 round-trip")
    except Exception as exc:
        add("authentication", "FAIL", str(exc))

    table = Table(title="GenoGuide doctor")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail", max_width=80)
    for name, status, detail in rows:
        color = "green" if status in {"PASS", "READY", "OPTIONAL"} else "red"
        table.add_row(name, f"[{color}]{status}[/{color}]", str(detail)[:80])
    console.print(table)
    return 0 if ok else 1
