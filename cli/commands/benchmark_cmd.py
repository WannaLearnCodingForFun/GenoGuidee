from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console()


def run(args) -> int:
    from research.training import train_baselines

    split_names = None if args.all else [s.strip() for s in args.splits.split(",") if s.strip()]
    out = train_baselines.run(config_path=args.config, split_names=split_names)

    for sname, sres in out["results"].items():
        t = Table(title=f"split: {sname}  (leakage: {sres['leakage']['severity']}, "
                        f"train={sres['sampled']['train']:,} test={sres['sampled']['test']:,})")
        for col in ("model", "AUPRC", "AUROC", "MCC", "bal.acc", "ECE(cal)", "bin AUROC"):
            t.add_column(col)
        for m, r in sres["models"].items():
            tc, tb = r["test_calibrated"], r.get("test_binary_path_spectrum", {})

            def f(x):
                return f"{x:.3f}" if isinstance(x, float) else "—"
            name = f"[bold green]{m} ⭐[/bold green]" if m == out["best_model"] and sname == "gene_disjoint" else m
            t.add_row(name, f(tc.get("macro_auprc_ovr")), f(tc.get("macro_auroc_ovr")),
                      f(tc.get("mcc")), f(tc.get("balanced_accuracy")),
                      f(tc.get("ece")), f(tb.get("auroc")))
        console.print(t)
    console.print(f"[green]best model (AUPRC→MCC→AUROC policy on gene-disjoint):[/green] {out['best_model']}")
    return 0
