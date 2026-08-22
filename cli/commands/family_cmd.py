from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console

console = Console()


def run(args) -> int:
    from app.phenotype.family import (
        analyze_trio, compound_het_candidates, couple_carrier_overlap)

    data = json.loads(Path(args.family_json).read_text())
    mode = data.get("mode", "trio")
    if mode == "couple":
        out = couple_carrier_overlap(data["partner_a"], data["partner_b"])
    else:
        child = data["child"]
        mother = data.get("mother") or []
        father = data.get("father") or []
        out = {
            **analyze_trio(child, mother, father),
            "compound_het": compound_het_candidates(child, mother, father),
        }
    console.print_json(data=out)
    return 0
