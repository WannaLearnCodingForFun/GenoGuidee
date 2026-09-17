"""Clinical evidence timeline for a variant. Feeds reanalysis."""
from __future__ import annotations

from typing import Any

from . import store


def timeline(variant_id: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    edges = store.execute(
        """SELECT edge_type, source, source_id, source_version, retrieved_at, evidence_strength, direction
           FROM evidence_graph_edges
           WHERE source_key=? OR target_key=? OR source_key=? OR target_key=?""",
        (variant_id, variant_id, f"variant:{variant_id}", f"variant:{variant_id}"),
        fetch="all",
    ) or []
    for e in edges:
        events.append({
            "when": e[4],
            "source": e[1],
            "source_id": e[2],
            "version": e[3],
            "kind": e[0],
            "strength": e[5],
            "direction": e[6],
        })
    vers = store.execute(
        """SELECT interpretation_id, version, classification, created_at, guideline_version, reviewer
           FROM interpretation_versions WHERE variant_id=? ORDER BY version ASC""",
        (variant_id,), fetch="all",
    ) or []
    for v in vers:
        events.append({
            "when": v[3],
            "source": "GenoGuide",
            "source_id": v[0],
            "version": f"interpretation-v{v[1]}",
            "kind": "INTERPRETATION",
            "classification": v[2],
            "guideline_version": v[4],
            "reviewer": v[5],
        })
    events.sort(key=lambda x: str(x.get("when") or ""))
    return events
