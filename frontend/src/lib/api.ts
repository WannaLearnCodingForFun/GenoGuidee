import { createClient } from "@/lib/supabase/client";

const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").trim() || "http://localhost:8000";
const TUNNEL_KEY = process.env.NEXT_PUBLIC_GENOGUIDE_TUNNEL_KEY ?? "";

// Phase B1: attach the current Supabase session's access token to every
// backend call so the FastAPI side can verify identity server-side instead
// of trusting a client-supplied role. Best-effort — if there's no session
// (e.g. demo/showcase browsing) requests still go out without the header,
// and routes that require it will 401.
async function authHeader(): Promise<Record<string, string>> {
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

async function apiHeaders(extra?: Record<string, string>): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "ngrok-skip-browser-warning": "true",
    ...(await authHeader()),
    ...extra,
  };
  if (TUNNEL_KEY) headers["X-GenoGuide-Key"] = TUNNEL_KEY;
  return headers;
}

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
    ml_bucket: string;
    acmg_bucket: string;
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

// --- Clinical workup: intake -> triple -> classification -> reconciliation
//     -> medication. Each stage is returned separately so the UI can reveal
//     them in order and show exactly where a run stopped.

export interface PatientHistory {
  age: number | null;
  sex: string | null;
  diagnosis: string | null;
  presenting_complaint: string | null;
  phenotypes: string[];
  prior_conditions: string[];
  medications: string[];
  family_history_positive: boolean;
  family_details: string | null;
  consent_confirmed: boolean;
}

export interface WorkupRequest {
  variant_id?: string | null;
  uploaded_variant?: UploadedAnalyzeRequest | null;
  history: PatientHistory;
  subject_ref?: string | null;
}

export interface WorkupStage {
  id: "intake" | "triple" | "classification" | "reconciliation" | "medication";
  label: string;
  status: string;
}

export interface WorkupTriple {
  gene: string | null;
  variant: string;
  variant_display: string;
  token_precision: "EXACT" | "GENE_LEVEL";
  token_note: string;
  disease: string | null;
  disease_source: string | null;
  gene_disease: string | null;
  guideline: string | null;
  complete: boolean;
}

export interface PhenotypeOverlap {
  status: "SUPPORTED" | "NO_OVERLAP" | "NO_HISTORY" | "NO_CURATED_ASSOCIATION";
  matched: string[];
  gene_keywords?: string[];
  note: string;
}

export interface MedicationStage {
  availability:
    | "AVAILABLE"
    | "NOT_INDICATED"
    | "INSUFFICIENT_INPUT"
    | "ENGINE_UNAVAILABLE"
    | "ENGINE_ERROR";
  reason?: string;
  query?: { gene: string; variant: string; disease: string };
  token_precision?: "EXACT" | "GENE_LEVEL";
  recommendations: TherapyRecommendation[];
  count?: number;
  human_review_required?: boolean;
  reconciliation_status?: string;
  advisory?: string;
  caution?: string | null;
  classification_gate?: string;
}

export interface WorkupResult {
  stages: WorkupStage[];
  variant: Variant;
  variant_source: "curated" | "upload";
  annotation_completeness: AnnotationCompleteness | null;
  missing_evidence: { criterion: string; reason: string }[];
  history_summary: {
    text: string;
    keywords: string[];
    age: number | null;
    sex: string | null;
    family_history_positive: boolean;
    phenotype_count: number;
    medication_count: number;
    prior_condition_count: number;
  };
  triple: WorkupTriple;
  esm2: AnalyzeResult["esm2"];
  ml: AnalyzeResult["ml"];
  acmg: AnalyzeResult["acmg"];
  reconciliation: AnalyzeResult["reconciliation"];
  phenotype_overlap: PhenotypeOverlap;
  medication: MedicationStage;
  considerations: { type: string; text: string }[];
  provenance: AnalyzeResult["provenance"];
  mode: string;
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
  const res = await fetch(`${API}${path}`, { headers: await apiHeaders() });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: await apiHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed (${res.status})`);
  return res.json();
}

async function postV1<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: await apiHeaders({
      "Content-Type": "application/json",
      "X-Role": "RESEARCHER",
    }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `${path} failed (${res.status})`;
    try {
      const err = await res.json();
      if (err?.detail) detail = typeof err.detail === "string" ? err.detail : detail;
    } catch {
      /* keep status text */
    }
    throw new Error(detail);
  }
  return res.json();
}

export interface TherapyRecommendation {
  drug: string;
  rank: number;
  score: number;
  response: string;
  evidence_level: string;
  evidence_count: number;
}

export interface SomaticTherapy {
  availability: "AVAILABLE" | "SOURCE_UNAVAILABLE" | "SOURCE_NOT_CONFIGURED" | "NOT_APPLICABLE" | "SKIPPED";
  reason: string | null;
  endpoint: string | null;
  request: { gene: string; variant: string; disease: string } | null;
  recommendations: TherapyRecommendation[];
  human_review_status: string;
  disclaimer: string;
  cached: boolean;
  latency_ms: number | null;
}

export interface TherapyStatus {
  enabled: boolean;
  url_configured: boolean;
  host?: string | null;
  url_error?: string | null;
  default: string;
  note: string;
  circuit_open: boolean;
  local_engine?: boolean;
}

export interface TherapyMap {
  protein_shorthand: string | null;
  indication: string | null;
  note: string;
}

export interface FrontendTherapyRequest {
  mutation: { gene: string; protein_change?: string; hgvs_p?: string; variant?: string };
  clinical: { indication?: string; disease?: string; diagnosis?: string };
}

export interface FrontendTherapyResponse {
  ok: boolean;
  layer: string;
  normalized: { gene: string; variant: string; disease: string };
  recommendation: SomaticTherapy;
  disclaimer: string;
}

export interface FrontendBridgeHealth {
  ok: boolean;
  layer: string;
  tunnel_key_required: boolean;
  connector: TherapyStatus;
  note: string;
}

export const api = {
  status: () => get<SystemStatus>("/api/status"),
  stats: () => get<Stats>("/api/stats"),
  variants: () => get<VariantListItem[]>("/api/variants"),
  analyze: (variant_id: string, patient_id?: string) =>
    post<AnalyzeResult>("/api/analyze", { variant_id, patient_id }),
  analyzeUploaded: (variant: UploadedAnalyzeRequest) =>
    post<UploadedAnalyzeResult>("/api/analyze/uploaded", variant),
  workup: (body: WorkupRequest) => post<WorkupResult>("/api/workup", body),
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
  therapyStatus: async () => {
    try {
      return await get<TherapyStatus>("/api/v1/therapy/status");
    } catch {
      await get<SystemStatus>("/api/status");
      return {
        enabled: true,
        url_configured: false,
        default: "GenoGuide API reachable — using in-repo drug engine when present",
        note: "somatic oncology ranking; never overrides ACMG",
        circuit_open: false,
        local_engine: true,
      };
    }
  },
  therapyMap: (hgvs_p: string, disease?: string) => {
    const q = new URLSearchParams({ hgvs_p });
    if (disease) q.set("disease", disease);
    return get<TherapyMap>(`/api/v1/therapy/map?${q.toString()}`);
  },
  therapyRecommend: async (gene: string, variant: string, disease: string) => {
    try {
      return await postV1<SomaticTherapy>("/api/v1/therapy/recommend", { gene, variant, disease });
    } catch {
      try {
        const bridged = await postV1<FrontendTherapyResponse>("/api/v1/frontend/therapy", {
          mutation: { gene, protein_change: variant },
          clinical: { indication: disease },
        });
        return bridged.recommendation;
      } catch {
        const raw = await post<{
          recommendations?: TherapyRecommendation[];
          gene?: string;
          variant?: string;
          disease?: string;
        }>("/drug-recommendation", { gene, variant, disease });
        return {
          availability: "AVAILABLE" as const,
          reason: "in-repo Medical_DrugRecommendation",
          endpoint: "/drug-recommendation",
          request: { gene, variant, disease },
          recommendations: raw.recommendations ?? [],
          human_review_status: "required",
          disclaimer: "Not a prescription. Does not alter ACMG.",
          cached: false,
          latency_ms: null,
        };
      }
    }
  },
  frontendHealth: () => get<FrontendBridgeHealth>("/api/v1/frontend/health"),
  frontendTherapy: (body: FrontendTherapyRequest) =>
    postV1<FrontendTherapyResponse>("/api/v1/frontend/therapy", body),
};
