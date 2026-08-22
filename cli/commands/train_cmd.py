from __future__ import annotations

from rich.console import Console

console = Console()


def run(args) -> int:
    from research.training import hardware, train_baselines

    hw = hardware.detect()
    console.print(f"[cyan]hardware:[/cyan] device={hw['device']} cpus={hw['cpu_count']} "
                  f"torch={hw['torch'] or 'not installed'}")
    console.print(f"[cyan]training from config[/cyan] {args.config}")
    out = train_baselines.run(config_path=args.config)
    console.print(f"[green]done[/green] experiment={out['experiment_id']} "
                  f"best={out['best_model']} → registered as {out['model_id']}")
    console.print("benchmark table → research/reports/benchmark_table.md")
    return 0
