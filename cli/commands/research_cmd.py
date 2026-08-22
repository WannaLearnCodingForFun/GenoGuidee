"""Lightweight research-run orchestrator: validate local artifacts + emit a report."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console

console = Console()
REPO = Path(__file__).resolve().parents[2]


def run(args) -> int:
    console.print("[bold cyan]GENOGUIDE RESEARCH RUN[/bold cyan]")
    steps = []

    from research import acquisition
    manifest = acquisition.load_manifest()
    present = sum(1 for n, s in manifest.items() if acquisition.dataset_status(n, s)["present"])
    steps.append(("data validation", True, f"{present}/{len(manifest)} sources present"))

    parquet = REPO / "research/data/processed/training_dataset.parquet"
    steps.append(("feature matrix", parquet.exists(), str(parquet)))

    leak = REPO / "research/reports/leakage_report.json"
    steps.append(("leakage report", leak.exists(), str(leak)))

    bench = REPO / "research/reports/benchmark_results.json"
    steps.append(("benchmark", bench.exists(), str(bench)))

    from research.training.registry import MODEL_STORE
    models = list((REPO / "models/registry").glob("*.json")) if (REPO / "models/registry").exists() else []
    steps.append(("model registry", bool(models), f"{len(models)} entries"))

    if getattr(args, "train", False) and parquet.exists():
        from research.training.train_baselines import run as train
        train(args.config)
        steps.append(("train", True, "completed"))

    ok = all(s[1] for s in steps)
    for name, good, detail in steps:
        mark = "[green]✓[/green]" if good else "[yellow]○[/yellow]"
        console.print(f"  {mark} {name:24} {detail}")
    console.print("\n[dim]Full retrain: python -m cli.genoguide train --config configs/model.yaml[/dim]")
    return 0 if ok else 1
