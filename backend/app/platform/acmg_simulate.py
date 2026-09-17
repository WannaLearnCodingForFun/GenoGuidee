"""ACMG what-if sandbox. Never persists as an official clinical interpretation."""
from __future__ import annotations

from typing import Any, Optional

from ..interpretation.acmg_v2 import CRITERIA_REGISTRY, combine
from ..schemas.interpretation import CriterionStrength

_STRENGTH = {
    "STAND_ALONE": CriterionStrength.STAND_ALONE,
    "VERY_STRONG": CriterionStrength.VERY_STRONG,
    "STRONG": CriterionStrength.STRONG,
    "MODERATE": CriterionStrength.MODERATE,
    "SUPPORTING": CriterionStrength.SUPPORTING,
}

_UP = {
    CriterionStrength.SUPPORTING: CriterionStrength.MODERATE,
    CriterionStrength.MODERATE: CriterionStrength.STRONG,
    CriterionStrength.STRONG: CriterionStrength.VERY_STRONG,
    CriterionStrength.VERY_STRONG: CriterionStrength.VERY_STRONG,
    CriterionStrength.STAND_ALONE: CriterionStrength.STAND_ALONE,
}
_DOWN = {
    CriterionStrength.VERY_STRONG: CriterionStrength.STRONG,
    CriterionStrength.STRONG: CriterionStrength.MODERATE,
    CriterionStrength.MODERATE: CriterionStrength.SUPPORTING,
    CriterionStrength.SUPPORTING: CriterionStrength.SUPPORTING,
    CriterionStrength.STAND_ALONE: CriterionStrength.STRONG,
}


def _met_from_official(official: dict[str, Any]) -> dict[str, tuple[CriterionStrength, str]]:
    met: dict[str, tuple[CriterionStrength, str]] = {}
    criteria = official.get("criteria") or []
    for c in criteria:
        status = str(c.get("status") or "")
        if status.endswith("MET") and "NOT_MET" not in status and "NOT_EVALUABLE" not in status:
            cid = c["id"]
            strength = _STRENGTH.get(str(c.get("applied_strength") or c.get("default_strength") or "SUPPORTING"),
                                     CriterionStrength.SUPPORTING)
            cat = c.get("category") or CRITERIA_REGISTRY[cid].category
            met[cid] = (strength, cat)
    for cid in official.get("met_criteria") or []:
        if cid not in met and cid in CRITERIA_REGISTRY:
            crit = CRITERIA_REGISTRY[cid]
            met[cid] = (crit.default_strength, crit.category)
    return met


def simulate(official: dict[str, Any], modifications: list[dict[str, Any]]) -> dict[str, Any]:
    met = _met_from_official(official)
    applied = []
    for mod in modifications:
        op = str(mod.get("op") or mod.get("action") or "").lower()
        cid = str(mod.get("criterion") or mod.get("id") or "").upper()
        if cid not in CRITERIA_REGISTRY and op != "remove":
            applied.append({"op": op, "criterion": cid, "ok": False, "reason": "unknown criterion"})
            continue
        if op in {"remove", "drop"}:
            met.pop(cid, None)
            applied.append({"op": "remove", "criterion": cid, "ok": True})
        elif op in {"add"}:
            crit = CRITERIA_REGISTRY[cid]
            strength = _STRENGTH.get(str(mod.get("strength") or "").upper(), crit.default_strength)
            met[cid] = (strength, crit.category)
            applied.append({"op": "add", "criterion": cid, "strength": strength.value, "ok": True})
        elif op in {"upgrade"}:
            if cid in met:
                met[cid] = (_UP[met[cid][0]], met[cid][1])
                applied.append({"op": "upgrade", "criterion": cid, "strength": met[cid][0].value, "ok": True})
            else:
                applied.append({"op": "upgrade", "criterion": cid, "ok": False, "reason": "not currently MET"})
        elif op in {"downgrade"}:
            if cid in met:
                met[cid] = (_DOWN[met[cid][0]], met[cid][1])
                applied.append({"op": "downgrade", "criterion": cid, "strength": met[cid][0].value, "ok": True})
            else:
                applied.append({"op": "downgrade", "criterion": cid, "ok": False, "reason": "not currently MET"})
        else:
            applied.append({"op": op, "criterion": cid, "ok": False, "reason": "unknown op"})

    triples = [(cid, s, cat) for cid, (s, cat) in met.items()]
    classification, rationale = combine(triples)
    official_cls = official.get("classification")
    from . import store
    store.execute(
        """INSERT INTO acmg_simulations
           (interpretation_id, official_classification, simulated_classification,
            modifications_json, result_json, created_at, official)
           VALUES (?,?,?,?,?,?,0)""",
        (official.get("interpretation_id"), official_cls, classification,
         store.dumps(modifications), store.dumps({"met": list(met), "rationale": rationale}),
         store.now()),
    )
    return {
        "simulation_only": True,
        "official_classification": official_cls,
        "simulated_classification": classification,
        "combining_rationale": rationale,
        "met_criteria": sorted(met),
        "modifications_applied": applied,
        "persisted_as_official": False,
        "note": "SIMULATION ONLY — does not modify the official interpretation.",
    }
