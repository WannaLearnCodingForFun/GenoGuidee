"""
ClinGen gene-specific ACMG specification layer.

Architecture:  generic engine → specification layer → gene-specific modifiers
→ final evidence strength. No gene's thresholds are ever hard-coded globally.

Specifications are YAML files in configs/clingen/<GENE>.yaml:

    name: BRCA1 VCEP spec (TEMPLATE)
    gene: BRCA1
    source: <URL of the ClinGen VCEP document>
    version: "1.0"
    status: TEMPLATE            # TEMPLATE | OFFICIAL
    thresholds:
      BA1_af: 0.001
    strength_overrides:
      PM2: SUPPORTING           # e.g. many VCEPs downgrade PM2
    disabled: [PP5, BP6]
    enabled: []                 # explicitly re-enable default-disabled criteria

IMPORTANT HONESTY RULE: files shipped with status TEMPLATE are structural
examples only — they do not assert real VCEP-approved values. The engine
records the spec name+status in every output so downstream consumers can
distinguish TEMPLATE from OFFICIAL specifications.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from ..schemas.interpretation import CriterionStrength

SPEC_DIR = Path(__file__).resolve().parents[3] / "configs" / "clingen"


class GeneSpecification:
    def __init__(self, data: dict):
        self.name: str = f"{data.get('name', 'unnamed')} [{data.get('status', 'TEMPLATE')}]"
        self.gene: str = data["gene"]
        self.version: str = str(data.get("version", "0"))
        self.status: str = data.get("status", "TEMPLATE")
        self.source: Optional[str] = data.get("source")
        self.threshold_overrides: dict[str, float] = dict(data.get("thresholds") or {})
        self._strength = {k: CriterionStrength(v) for k, v in (data.get("strength_overrides") or {}).items()}
        self._disabled = set(data.get("disabled") or [])
        self._enabled = set(data.get("enabled") or [])

    def criterion_enabled(self, cid: str, default: bool) -> bool:
        if cid in self._disabled:
            return False
        if cid in self._enabled:
            return True
        return default

    def applied_strength(self, cid: str, default: CriterionStrength) -> CriterionStrength:
        return self._strength.get(cid, default)


def load_specification(gene: str | None) -> Optional[GeneSpecification]:
    if not gene:
        return None
    path = SPEC_DIR / f"{gene.upper()}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        return GeneSpecification(yaml.safe_load(f))


def list_specifications() -> list[dict]:
    if not SPEC_DIR.exists():
        return []
    out = []
    for p in sorted(SPEC_DIR.glob("*.yaml")):
        with open(p) as f:
            d = yaml.safe_load(f)
        out.append({"gene": d.get("gene"), "name": d.get("name"),
                    "status": d.get("status", "TEMPLATE"), "version": d.get("version")})
    return out
