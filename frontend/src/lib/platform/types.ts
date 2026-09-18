/** Types matching backend/app/api/platform.py JSON bodies. */

export type RadarState = "CONCORDANT" | "MIXED" | "CONFLICTING" | "INSUFFICIENT";
export type EvidenceCategory =
  | "PATHOGENIC_SUPPORT"
  | "BENIGN_SUPPORT"
  | "UNCERTAIN"
  | "CONFLICTING"
  | "MISSING";

export interface RadarItem {
  name: string;
  category: EvidenceCategory | string;
  detail: string | number | boolean | Record<string, unknown> | null;
  source: string;
}

export interface EvidenceRadar {
  overall_state: RadarState | string;
  supporting_evidence: RadarItem[];
  contradicting_evidence: RadarItem[];
  unknown_evidence: RadarItem[];
  confidence: number;
  human_review_required: boolean;
  items: RadarItem[];
  note?: string;
}

export interface PlatformGraphNode {
  key: string;
  type: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface PlatformGraphEdge {
  source_key: string;
  target_key: string;
  edge_type: string;
  source?: string | null;
  source_id?: string | null;
  source_version?: string | null;
  retrieved_at?: string | null;
  evidence_strength?: string | null;
  direction?: string | null;
  properties?: Record<string, unknown>;
}

export interface PlatformGraph {
  kg_version: string;
  seed: string;
  nodes: PlatformGraphNode[];
  edges: PlatformGraphEdge[];
}

export interface InterpretationVersion {
  interpretation_id: string;
  version: number;
  variant_id: string | null;
  classification: string;
  acmg_criteria: Record<string, unknown>;
  ml_prediction: Record<string, unknown> | null;
  model_version: string | null;
  phenotype_score: number | null;
  evidence_ids: string[];
  kg_version: string | null;
  guideline_version: string | null;
  reviewer: string | null;
  curation_state: string;
  payload: Record<string, unknown>;
  provenance: Record<string, unknown>;
  created_at: number;
}

export interface InterpretationDiff {
  interpretation_id: string;
  version_a: number;
  version_b: number;
  new_evidence: string[];
  removed_evidence: string[];
  changed_acmg_criteria: { criterion: string; before?: string; after?: string }[];
  changed_model_probability: { before: number | null; after: number | null };
  changed_phenotype_score: { before: number | null; after: number | null };
  changed_classification: { before: string; after: string };
  changed_reviewer_decision: Record<string, unknown>;
  summary: string;
  deterministic: boolean;
}

export interface ReanalysisCheck {
  sources: Record<string, Record<string, unknown>>;
  changes: { source: string; previous_fingerprint: string | null; current_fingerprint: string; version?: string }[];
  changed: boolean;
}

export interface ReanalysisRun {
  job_id: string;
  status: string;
  source_changes: ReanalysisCheck["changes"];
  affected: Record<string, unknown>[];
  auto_finalized: boolean;
}

export interface ReanalysisJob {
  job_id: string;
  status: string;
  created_at: number;
  finished_at: number | null;
  payload: Record<string, unknown>;
}

export interface ReanalysisChange {
  job_id: string;
  variant_id: string | null;
  interpretation_id: string | null;
  change_type: string;
  payload: Record<string, unknown>;
  created_at: number;
}

export interface PhenotypeNormalize {
  terms: {
    input: string;
    hpo_id: string | null;
    label: string;
    negated: boolean;
    resolved: boolean;
    match_type: string;
    onset?: string;
    severity?: string;
  }[];
  positive_hpo: string[];
  negated_hpo: string[];
  unresolved: string[];
  note: string;
}

export interface InheritanceResult {
  inheritance_model: string;
  candidate_variants: { variant_id: string; gene?: string; zygosity?: string; de_novo_candidate?: boolean }[];
  phase_status: "UNKNOWN" | "CIS" | "TRANS" | "INFERRED" | string;
  evidence: string[];
  confidence: number;
  human_review_required: boolean;
  trio?: Record<string, unknown>;
  compound_het?: Record<string, unknown>;
  x_linked_flagged?: string[];
  mitochondrial_flagged?: string[];
  note?: string;
}

export interface ACMGSimulation {
  simulation_only: boolean;
  official_classification: string | null;
  simulated_classification: string;
  combining_rationale: string;
  met_criteria: string[];
  modifications_applied: Record<string, unknown>[];
  persisted_as_official: boolean;
  note: string;
}

export interface ModelOODResult {
  prediction?: string | null;
  calibrated_probability?: number | null;
  entropy?: number | null;
  uncertainty?: number | null;
  OOD_score?: number | null;
  OOD_state?: string | null;
  model_version?: string | null;
  human_review_required: boolean;
  reason?: string;
}

export interface DriftSnapshot {
  n: number;
  class_distribution?: Record<string, number>;
  training_prior?: Record<string, number>;
  total_variation?: number;
  drift_level: string;
  ood_rate?: number;
  missingness?: number;
  mean_entropy?: number | null;
  gene_distribution?: [string, number][];
  action?: string;
  retrained: boolean;
  note?: string;
  created_at?: number;
}

export interface GeneRankItem {
  gene: string;
  phenotype_match_score: number | null;
  n_profile_terms?: number;
  note?: string;
}

export interface DiseaseRankItem {
  disease_id: string;
  disease_name: string;
  phenotype_match_score: number;
}

export interface PhenotypeRanking<T> {
  measure?: string;
  hpo_version?: string;
  patient_terms_resolved?: string[];
  unknown_terms?: string[];
  ranking?: T[];
  normalized?: PhenotypeNormalize;
  acmg_altered?: boolean;
  availability?: string;
  reason?: string;
}

export interface PhenotypeMatchResult {
  availability: string;
  reason?: string;
  normalized?: PhenotypeNormalize;
  gene?: Record<string, unknown>;
  genes?: PhenotypeRanking<GeneRankItem>;
  diseases?: PhenotypeRanking<DiseaseRankItem>;
}

export interface ACMGCriterionRow {
  id: string;
  name: string;
  status: string;
  category: string;
  default_strength: string;
  applied_strength?: string | null;
  reason: string;
  sources: string[];
}

export interface ACMGEvaluateResult {
  classification: string;
  met_criteria: string[];
  criteria: ACMGCriterionRow[];
  combining_rationale?: string;
  rule_version?: string;
}

export type EvidenceFilter = "All" | "Supporting" | "Contradicting" | "Uncertain" | "Missing";
