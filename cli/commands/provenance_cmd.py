from __future__ import annotations

from rich.console import Console

console = Console()


def run(args) -> int:
    from app.provenance2 import ledger

    if args.action == "verify":
        if not args.id:
            chain = ledger.verify_chain()
            console.print(f"chain: {'[green]VALID[/green]' if chain['valid'] else '[red]INVALID[/red]'} "
                          f"({chain.get('blocks', 0)} blocks)")
            return 0 if chain["valid"] else 1
        result = ledger.verify_interpretation(args.id)
        console.print(f"{args.id}: "
                      f"{'[green]VERIFIED[/green]' if result['verified'] else '[red]FAILED[/red]'}")
        if result.get("record"):
            r = result["record"]
            console.print(f"  tx={r['tx_id']} block={r['block_index']}")
            console.print(f"  model={r['model_version']} acmg={r['acmg_rule_version']}")
            console.print(f"  input={r['input_hash'][:20]}… output={r['output_hash'][:20]}…")
        return 0 if result["verified"] else 1

    if args.action == "audit":
        for b in ledger.audit_trail(15):
            console.print(f"  [{b['block_index']:>4}] {b['interpretation_id']}  tx={b['tx_id']}  "
                          f"model={b.get('model_version') or '—'}")
        chain = ledger.verify_chain()
        console.print(f"chain integrity: {'[green]VALID[/green]' if chain['valid'] else '[red]INVALID[/red]'}")
        return 0
    return 2
