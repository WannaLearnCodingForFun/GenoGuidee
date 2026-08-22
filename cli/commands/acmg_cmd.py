from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

console = Console()


def run(args) -> int:
    from app.interpretation.acmg_v2 import EvidenceInputs, evaluate
    from app.interpretation.clingen_specs import load_specification

    data = json.loads(Path(args.evidence_json).read_text())
    gene = (data.get("gene_context") or {}).get("gene")
    result = evaluate(EvidenceInputs(**data), load_specification(gene))
    console.print_json(result.model_dump_json(indent=2))
    return 0
