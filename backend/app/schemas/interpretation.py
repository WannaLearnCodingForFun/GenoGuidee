"""
Canonical interpretation object — the central contract between the research
engine and any future frontend (documented in docs/API_CONTRACT.md).

Every field group is optional-but-explicit: absence of evidence is represented
as an explicit availability state, never silently treated as negative or
positive evidence.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .therapy import SomaticTherapy
from .variant import CanonicalVariant


class EvidenceAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    NOT_AVAILABLE = "NOT_AVAILABLE"       # source exists, no data for this variant
    SOURCE_NOT_CONFIGURED = "SOURCE_NOT_CONFIGURED"  # connector not installed/licensed


class CriterionStrength(str, Enum):
    STAND_ALONE = "STAND_ALONE"
    VERY_STRONG = "VERY_STRONG"
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    SUPPORTING = "SUPPORTING"


class CriterionStatus(str, Enum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    NOT_EVALUABLE = "NOT_EVALUABLE"  # required evidence input absent


class AcmgCriterionResult(BaseModel):
    id: str
    name: str
    category: str                       # pathogenic | benign
    default_strength: CriterionStrength
    applied_strength: Optional[CriterionStrength] = None  # after ClinGen modifiers
    status: CriterionStatus
    reason: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    rule_version: str
    gene_specification: Optional[str] = None
    timestamp: str


class AcmgInterpretation(BaseModel):
    classification: str
    criteria: list[AcmgCriterionResult]
    met_criteria: list[str]
    not_evaluable: list[str]
    rule_version: str
    gene_specification: Optional[str] = None
    combining_rationale: str
    confidence: str
    human_review_required: bool


class MlPrediction(BaseModel):
    model_id: str
    model_version: str
    probabilities: dict[str, float]
    top_class: str
    calibrated: bool
    calibrated_probabilities: Optional[dict[str, float]] = None
    uncertainty: Optional[dict[str, float]] = None   # entropy, max_prob, ensemble_var
    ood: Optional[dict[str, Any]] = None             # state + distance metrics
    feature_attributions: Optional[list[dict[str, Any]]] = None


class Reconciliation(BaseModel):
    status: str                         # CONCORDANT | DISCORDANT | ML_UNAVAILABLE
    ml_bucket: Optional[str]
    acmg_bucket: str
    final_classification: str           # ALWAYS the ACMG classification
    authority: str = "ACMG/AMP rule engine — ML never overrides deterministic evidence"
    human_review_required: bool
    note: str


class ClinicalConsideration(BaseModel):
    type: str
    text: str
    reason: str
    sources: list[str] = Field(default_factory=list)
    guideline: Optional[str] = None
    version: Optional[str] = None
    confidence: str = "advisory"
    human_review_status: str = "not_reviewed"


class ProvenanceRecord(BaseModel):
    interpretation_id: str
    input_hash: str
    output_hash: str
    annotation_version: Optional[str]
    model_version: Optional[str]
    model_hash: Optional[str]
    acmg_rule_version: str
    knowledge_graph_version: Optional[str]
    phenotype_version: Optional[str]
    evidence_snapshot_hash: Optional[str]
    timestamp: str
    operator: str
    tx_id: Optional[str] = None


class InterpretationObject(BaseModel):
    """Section-76 canonical object."""
    variant: CanonicalVariant
    annotation: dict[str, Any] = Field(default_factory=dict)
    population_evidence: dict[str, Any] = Field(default_factory=dict)
    functional_evidence: dict[str, Any] = Field(default_factory=dict)
    sequence_model: dict[str, Any] = Field(default_factory=dict)
    ml_prediction: Optional[MlPrediction] = None
    acmg_interpretation: AcmgInterpretation
    reconciliation: Reconciliation
    phenotype_match: dict[str, Any] = Field(default_factory=dict)
    gene_disease_context: dict[str, Any] = Field(default_factory=dict)
    clinical_evidence: dict[str, Any] = Field(default_factory=dict)
    clinical_considerations: list[ClinicalConsideration] = Field(default_factory=list)
    somatic_therapy: Optional[SomaticTherapy] = None
    uncertainty: dict[str, Any] = Field(default_factory=dict)
    human_review: dict[str, Any] = Field(default_factory=dict)
    provenance: Optional[ProvenanceRecord] = None
