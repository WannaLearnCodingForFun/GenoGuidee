const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Types mirroring the FastAPI response models
// ---------------------------------------------------------------------------

export interface Variant {
  id: string;
  gene: string;
  transcript: string;
  hgvs_c: string;
  hgvs_p: string;
  chrom: string;
  pos: number;
  consequence: string;
  gnomad_af: number;
  cadd: number | null;
  revel: number | null;
  spliceai: number | null;
  phylop: number | null;
  hotspot_domain: string | null;
  functional_evidence: string | null;
  condition: string;
  inheritance: string;
  showcase: boolean;
  showcase_label: string | null;
  public_note: string;
}

export interface VariantListItem {
  id: string;
  gene: string;
  hgvs_c: string;
  hgvs_p: string;
  consequence: string;
  gnomad_af: number;
  showcase: boolean;
  showcase_label: string | null;
  condition: string;
}

export interface AcmgCriterion {
  id: string;
  name: string;
  strength: string;
  status: "MET" | "NOT_MET";
  met: boolean;
  reason: string;
  evidence_source: string;
}

export interface AnalyzeResult {
  variant: Variant;
  esm2: {
    mode: string;
    model: string;
    dims: number;
    embedding_preview: number[];
    delta_score: number;
  };
  ml: {
    probabilities: Record<string, number>;
    top_class: string;
    top_class_key: string;
    confidence: number;
    engine: string;
    model_version: string;
  };
  acmg: {
    criteria: AcmgCriterion[];
    met: AcmgCriterion[];
    classification: string;
    met_criteria: string[];
    rule_note: string;
    framework: string;
  };
  reconciliation: {
    status: "CONCORDANT" | "DISCORDANT";
    confidence: string;
    final_classification: string;
    authority: string;
    note: string;
  };
  provenance: {
    recorded: boolean;
    contract: string;
    tx_id: string;
    block_index: number;
    interpretation_hash: string;
    patient_hash: string;
    model_version: string;
    evidence_version: string;
    timestamp: number;
  };
  mode: string;
}

export interface AnnotationCompleteness {
  present: number;
  total: number;
  percent: number;
  level: "HIGH" | "PARTIAL" | "LOW";
  fields: Record<string, boolean>;
}

export interface UploadedAnalyzeRequest {
  chrom: string;
  pos: number;
  ref: string;
  alt: string;
  gene?: string | null;
  transcript?: string | null;
  hgvs_c?: string | null;
  hgvs_p?: string | null;
  consequence?: string | null;
  gnomad_af?: number | null;
  cadd?: number | null;
  revel?: number | null;
  spliceai?: number | null;
  phylop?: number | null;
  subject_ref?: string | null;
  upload_id?: string | null;
}

export interface UploadedAnalyzeResult extends AnalyzeResult {
  annotation_completeness: AnnotationCompleteness;
  missing_evidence: { criterion: string; reason: string }[];
  source: "upload";
}

export interface Patient {
  id: string;
  synthetic: boolean;
  label: string;
  age: number;
  sex: string;
  diagnosis: string;
  diagnosis_short: string;
  phenotypes: { hpo: string; term: string }[];
  family_history: { positive: boolean; entries: string[] };
  medications: { name: string; dose: string; pgx_gene: string | null; pgx_note: string | null }[];
  variant_ids: string[];
  primary_variant_id: string;
  genome_stats: { total_variants: number; candidates: number; annotated: number; prioritized: number };
  consent_scope: string;
}

export interface ContextAnalysis {
  variant: Variant;
  acmg_classification: string;
  acmg_met: string[];
  ml_top_class: string;
  ml_confidence: number;
  phenotype_matched_terms: string[];
  gene_disease: string | null;
  guideline: string | null;
  relevance: {
    score: number;
    level: "HIGH" | "MODERATE" | "LOW";
    components: { name: string; value: number; max: number }[];
  };
  considerations: { type: string; text: string }[];
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  sublabel: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

export interface LedgerBlock {
  block_index: number;
  tx_id: string;
  contract: string;
  function: string;
  subject_id: string;
  payload: Record<string, unknown>;
  payload_hash: string;
  prev_hash: string;
  block_hash: string;
  timestamp: number;
  channel: string;
}

export interface VerifyResult {
  verified: boolean;
  status: string;
  tx_id: string;
  record?: LedgerBlock;
  checks: { block_index: number; tx_id: string; intact: boolean }[];
  chain_depth: number;
}

export interface SystemStatus {
  mode: string;
  components: { name: string; ready: boolean; detail: Record<string, unknown> }[];
  model_version: string;
  evidence_version: string;
}

export interface Stats {
  patients: number;
  variants_analyzed: number;
  high_priority_variants: number;
  verified_interpretations: number;
  dataset_variants: number;
  showcase_variants: number;
}

// ---------------------------------------------------------------------------
// Fetch helpers
// ---------------------------------------------------------------------------

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

export const api = {
  status: () => get<SystemStatus>("/api/status"),
  stats: () => get<Stats>("/api/stats"),
  variants: () => get<VariantListItem[]>("/api/variants"),
  analyze: (variant_id: string, patient_id?: string) =>
    post<AnalyzeResult>("/api/analyze", { variant_id, patient_id }),
  analyzeUploaded: (variant: UploadedAnalyzeRequest) =>
    post<UploadedAnalyzeResult>("/api/analyze/uploaded", variant),
  patients: () => get<Patient[]>("/api/patients"),
  patientContext: (id: string) =>
    get<{ patient: Patient; analyses: ContextAnalysis[] }>(`/api/patients/${id}/context`),
  graph: (patientId: string) =>
    get<{ nodes: GraphNode[]; edges: GraphEdge[]; patient_id: string }>(`/api/graph/${patientId}`),
  audit: (patientId?: string) =>
    get<{ blocks: LedgerBlock[]; stats: Record<string, unknown>; contracts: string[]; contract_functions: string[] }>(
      `/api/provenance/audit${patientId ? `?patient_id=${patientId}` : ""}`,
    ),
  verify: (tx_id: string) => post<VerifyResult>("/api/provenance/verify", { tx_id }),
  consent: (patientId: string) =>
    get<{ patient_id: string; state: string; record: LedgerBlock | null; history_length: number }>(
      `/api/provenance/consent/${patientId}`,
    ),
  recordConsent: (patient_id: string) => post<LedgerBlock>("/api/provenance/consent/record", { patient_id }),
  revokeConsent: (patient_id: string) => post<LedgerBlock>("/api/provenance/consent/revoke", { patient_id }),
};
