from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def run() -> int:
    import pandas as pd

    from research.evaluation import leakage, splits as S
    from research.training.train_baselines import REPO

    df = pd.read_parquet(REPO / "research/data/processed/training_dataset.parquet")
    split_objs = {name: fn(df) for name, fn in S.SPLITTERS.items()}
    report = leakage.run_audit(df, split_objs)

    t = Table(title=f"Leakage audit — {report['n_rows']:,} rows")
    for col in ("split", "coord overlap", "VariationID overlap", "gene+protein overlap", "severity"):
        t.add_column(col)
    for name, r in report["splits"].items():
        sev = r["severity"]
        color = {"OK": "green", "WARNING": "yellow", "SEVERE": "red"}[sev]
        t.add_row(name, str(r["exact_coordinate_overlap"]), str(r["variation_id_overlap"]),
                  f"{r['gene_protein_change_overlap']} ({r['gene_protein_change_overlap_fraction']:.3%})",
                  f"[{color}]{sev}[/{color}]")
    console.print(t)
    console.print("reports → research/reports/leakage_report.{json,html}")
    return 0
