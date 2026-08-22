"""
Phase B5 — pure gate deciding whether therapy ranking may run at all.

No I/O. `final_classification` and `review_status` are strings so callers can
pass whatever their persistence layer uses without this module depending on
it. Rules (clinical, not an engineering default — see docs/PLAN_BACKEND_FRONTEND.md
Phase B5):
  - allow only if final_classification in {pathogenic, likely_pathogenic}
  - never allow if therapy_addressable is False
  - never allow unless the interpretation has been reviewed/signed off
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

ALLOWED_CLASSIFICATIONS = {"pathogenic", "likely_pathogenic"}
REVIEWED_STATUSES = {"reviewed", "signed_off"}


@dataclass
class GateResult:
    allow: bool
    reason: Optional[str]


def gate(
    final_classification: Optional[str],
    therapy_addressable: bool,
    review_status: Optional[str],
) -> GateResult:
    classification = (final_classification or "").strip().lower()

    if not therapy_addressable:
        return GateResult(False, "variant is not therapy-addressable (not a single-residue substitution)")

    if classification not in ALLOWED_CLASSIFICATIONS:
        return GateResult(
            False,
            f"classification {classification or '<none>'!r} does not meet the "
            "pathogenic/likely_pathogenic bar for therapy ranking",
        )

    if (review_status or "").strip().lower() not in REVIEWED_STATUSES:
        return GateResult(False, "interpretation has not been reviewed/signed off by a doctor")

    return GateResult(True, None)
