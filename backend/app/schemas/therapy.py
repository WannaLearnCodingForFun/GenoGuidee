"""
Somatic oncology therapy ranking — advisory payload only.

This block is attached to InterpretationObject as an OPTIONAL sibling of
clinical_considerations. It never replaces ACMG, ML, PGx, or CDS v2.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TherapyAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"       # connector on, remote failed
    SOURCE_NOT_CONFIGURED = "SOURCE_NOT_CONFIGURED"  # env flag off / no URL
    NOT_APPLICABLE = "NOT_APPLICABLE"                # germline / wrong biology
    SKIPPED = "SKIPPED"                              # unmappable protein/disease


class TherapyRecommendation(BaseModel):
    drug: str
    rank: int
    score: float
    response: str
    evidence_level: str
    evidence_count: int


class SomaticTherapy(BaseModel):
    availability: TherapyAvailability
    reason: Optional[str] = None
    endpoint: Optional[str] = None
    request: Optional[dict[str, str]] = None
    request_hash: Optional[str] = None
    response_hash: Optional[str] = None
    recommendations: list[TherapyRecommendation] = Field(default_factory=list)
    human_review_status: str = "required"
    disclaimer: str = (
        "External oncology ranking from a separate engine. Not a prescription. "
        "Does not alter ACMG/AMP classification. Review applicable oncology "
        "guidelines with a qualified specialist before any treatment decision. "
        "No patient identifiers are sent to the remote service."
    )
    cached: bool = False
    latency_ms: Optional[float] = None
    engine: Optional[dict[str, Any]] = None
    abstained: bool = False
