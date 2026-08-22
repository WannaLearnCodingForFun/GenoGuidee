from __future__ import annotations

from rich.console import Console
from rich.table import Table

from research import acquisition

console = Console()


def run(args) -> int:
    if args.action == "list":
        manifest = acquisition.load_manifest()
        table = Table(title="GenoGuide datasets (research/data/manifest.yaml)")
        table.add_column("dataset", style="cyan")
        table.add_column("present")
        table.add_column("auto-dl")
        table.add_column("license", max_width=42)
        table.add_column("receipt")
        for name, spec in manifest.items():
            st = acquisition.dataset_status(name, spec)
            table.add_row(
                name,
                "[green]yes[/green]" if st["present"] else "[dim]no[/dim]",
                "yes" if st["auto_downloadable"] else "[yellow]manual[/yellow]",
                st["license"],
                st["receipt"]["download_date"][:10] if st["receipt"] else "[dim]—[/dim]",
            )
        console.print(table)
        return 0

    if args.action == "download":
        if not args.dataset:
            console.print("[red]usage: data download <dataset>[/red]")
            return 2
        try:
            receipt = acquisition.download(args.dataset, force=args.force)
        except (KeyError, RuntimeError) as e:
            console.print(f"[red]{e}[/red]")
            return 1
        console.print(f"[green]downloaded {args.dataset}[/green]")
        for f in receipt["files"]:
            console.print(f"  {f['file']}  {f['size_bytes']:,} bytes  sha256={f['sha256'][:16]}…")
        return 0

    if args.action == "verify":
        results = acquisition.verify(args.dataset)
        ok = True
        for r in results:
            status = r["status"]
            color = "green" if status == "VERIFIED" else ("yellow" if status == "NO_RECEIPT" else "red")
            ok = ok and status in ("VERIFIED", "NO_RECEIPT")
            console.print(f"  [{color}]{status:18}[/{color}] {r['dataset']}" + (f" ({r.get('file')})" if r.get("file") else ""))
        return 0 if ok else 1
    return 2
