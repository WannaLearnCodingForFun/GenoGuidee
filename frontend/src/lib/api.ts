import { createClient } from "@/lib/supabase/client";

const API = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").trim() || "http://localhost:8000";
const TUNNEL_KEY = process.env.NEXT_PUBLIC_GENOGUIDE_TUNNEL_KEY ?? "";

// Phase B1: attach the current Supabase session's access token to every
// backend call so the FastAPI side can verify identity server-side instead
// of trusting a client-supplied role. Best-effort — if there's no session
// (e.g. demo/showcase browsing) requests still go out without the header,
// and routes that require it will 401.
const LOCAL_TOKEN_KEY = "genoguide_token";

export function getLocalToken(): string | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(LOCAL_TOKEN_KEY);
  if (stored) return stored;
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOCAL_TOKEN_KEY}=([^;]*)`));
  const fromCookie = match ? decodeURIComponent(match[1]) : "";
  if (fromCookie) {
    window.localStorage.setItem(LOCAL_TOKEN_KEY, fromCookie);
    return fromCookie;
  }
  return null;
}

export function setLocalToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(LOCAL_TOKEN_KEY, token);
    document.cookie = `${LOCAL_TOKEN_KEY}=${encodeURIComponent(token)}; Path=/; Max-Age=${7 * 86400}; SameSite=Lax`;
  } else {
    window.localStorage.removeItem(LOCAL_TOKEN_KEY);
    document.cookie = `${LOCAL_TOKEN_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const local = getLocalToken();
  if (local) return { Authorization: `Bearer ${local}` };
  try {
    const supabase = createClient();
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (token) return { Authorization: `Bearer ${token}` };
  } catch {
    /* no session */
  }
  return {};
}

function describeHttpError(path: string, status: number, detail?: string): string {
  if (status === 0 || status === 502 || status === 503 || status === 504) {
    if (path.includes("therapy")) {
      return "THERAPY SERVICE UNAVAILABLE — the local backend is running, but the therapy ranker did not respond.";
    }
    return "BACKEND UNAVAILABLE — unable to connect to the GenoGuide API. Check that the backend is running on port 8000.";
  }
  if (detail) return detail;
  return `${path} failed (${status})`;
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
  ref?: string;
  alt?: string;
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
  observation_status?: string;
  source_type?: string;
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

export interface HealthComponent {
  status: "READY" | "DEGRADED" | "OFFLINE" | "NOT_CONFIGURED" | "ERROR";
  detail: string;
}

export interface HealthReport {
  status: "READY" | "DEGRADED" | "FAILED";
  ok: boolean;
  components: Record<string, HealthComponent>;
  demo_mode?: boolean;
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
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, { headers: await apiHeaders() });
  } catch {
    throw new Error(
      "BACKEND UNAVAILABLE — unable to connect to the GenoGuide API. Check that the backend is running on port 8000.",
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      if (err?.detail) detail = typeof err.detail === "string" ? err.detail : "";
    } catch {
      /* keep status */
    }
    throw new Error(describeHttpError(path, res.status, detail));
  }
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: await apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "BACKEND UNAVAILABLE — unable to connect to the GenoGuide API. Check that the backend is running on port 8000.",
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      if (err?.detail) detail = typeof err.detail === "string" ? err.detail : "";
    } catch {
      /* keep status */
    }
    throw new Error(describeHttpError(path, res.status, detail));
  }
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method: "PATCH",
      headers: await apiHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "BACKEND UNAVAILABLE — unable to connect to the GenoGuide API. Check that the backend is running on port 8000.",
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      if (err?.detail) detail = typeof err.detail === "string" ? err.detail : "";
    } catch {
      /* keep status */
    }
    throw new Error(describeHttpError(path, res.status, detail));
  }
  return res.json();
}

async function postV1<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: await apiHeaders({
        "Content-Type": "application/json",
        "X-Role": "RESEARCHER",
      }),
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "BACKEND UNAVAILABLE — unable to connect to the GenoGuide API. Check that the backend is running on port 8000.",
    );
  }
  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      if (err?.detail) detail = typeof err.detail === "string" ? err.detail : "";
    } catch {
      /* keep status text */
    }
    throw new Error(describeHttpError(path, res.status, detail));
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
  abstained?: boolean;
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
  health: () => get<HealthReport>("/health"),
  healthDetailed: () => get<HealthReport>("/health/detailed"),
  status: () => get<SystemStatus>("/api/status"),
  stats: () => get<Stats>("/api/stats"),
  variants: () => get<VariantListItem[]>("/api/variants"),
  variant: (id: string) => get<Variant>(`/api/variants/${id}`),
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
  signup: (body: {
    email: string;
    password: string;
    full_name: string;
    role: string;
    invite_token?: string;
  }) =>
    post<{
      token: string;
      user: { id: number; email: string; role: string; full_name: string };
      patient?: { id: number; uuid: string; identifier: string } | null;
    }>("/api/auth/signup", body),
  login: (body: { email: string; password: string; patient_id?: string }) =>
    post<{
      token: string;
      user: { id: number; email: string; role: string; full_name: string };
      patient?: ClinicalPatient | null;
    }>("/api/auth/login", body),
  me: () =>
    get<{
      id: number;
      email: string;
      role: string;
      full_name: string;
      patient?: Record<string, unknown> | null;
      linked?: boolean;
    }>("/api/auth/me"),
  patientMe: () =>
    get<{
      linked: boolean;
      message?: string;
      patient: ClinicalPatient | null;
      uploads?: ClinicalUpload[];
      report?: Record<string, unknown> | null;
      reconciliations?: { final_classification: string; confidence?: string }[];
      workup?: WorkupSnapshot | null;
      longitudinal?: { message: string | null; trajectory_available: boolean };
    }>("/api/patient/me"),
  patientClaim: (invite_token: string) =>
    post<{ linked: boolean; patient: ClinicalPatient }>("/api/patient/claim", { invite_token }),
  clinicalInvite: (patientId: number) =>
    post<{
      patient: ClinicalPatient;
      invitation: { token: string; account_status: string; signup_path: string };
    }>(`/api/clinical/patients/${patientId}/invite`, {}),
  clinicalOverview: () =>
    get<{
      user: { id: number; email: string; role: string; full_name: string };
      patients: Record<string, unknown>[];
      uploads: Record<string, unknown>[];
      pending_signoffs: number;
      counts: Record<string, number>;
    }>("/api/clinical/overview"),
  clinicalPatients: () => get<ClinicalPatient[]>("/api/clinical/patients"),
  clinicalLookupPatient: (identifier: string) =>
    get<{
      id: number;
      identifier: string;
      full_name: string | null;
      email: string | null;
      account_status: string;
    }>(`/api/clinical/patient-lookup?identifier=${encodeURIComponent(identifier)}`),
  clinicalPatient: (id: number) => get<ClinicalBundle>(`/api/clinical/patients/${id}`),
  clinicalWorkup: (body: Record<string, unknown>) =>
    post<{
      patient: ClinicalPatient;
      bundle: ClinicalBundle;
      interpretation: unknown;
      invitation?: { token: string; signup_path: string; account_status: string } | null;
    }>("/api/clinical/workup", body),
  clinicalUploads: () => get<ClinicalUpload[]>("/api/clinical/uploads"),
  clinicalUpload: (id: number) =>
    get<ClinicalUpload & { variants: ClinicalVariant[] }>(`/api/clinical/uploads/${id}`),
  clinicalAssign: (uploadId: number, patient_id: number | null) =>
    post<ClinicalUpload>(`/api/clinical/uploads/${uploadId}/assign`, { patient_id }),
  clinicalVariants: (page = 1) =>
    get<{ items: ClinicalVariant[]; total: number }>(`/api/clinical/variants?page=${page}&page_size=50`),
  clinicalInterpret: (variantId: number, patientId?: number) =>
    post<Record<string, unknown>>(
      `/api/clinical/variants/${variantId}/interpret${patientId ? `?patient_id=${patientId}` : ""}`,
      {},
    ),
  clinicalGraph: (patientId: number) =>
    get<{ nodes: GraphNode[]; edges: GraphEdge[]; patient_id: number }>(
      `/api/clinical/patients/${patientId}/graph`,
    ),
  clinicalProvenance: (patientId: number) =>
    get<{ blocks: Record<string, unknown>[]; block_count: number; interpretations: number }>(
      `/api/clinical/patients/${patientId}/provenance`,
    ),
  clinicalConsent: (patientId: number) =>
    get<{ patient_id: string; state: string; records: Record<string, unknown>[] }>(
      `/api/clinical/patients/${patientId}/consent`,
    ),
  clinicalAudit: (patientId: number) =>
    get<{ events: Record<string, unknown>[] }>(`/api/clinical/patients/${patientId}/audit`),
  clinicalVerify: (block_id: number) =>
    post<Record<string, unknown>>("/api/clinical/provenance/verify", { block_id }),
  clinicalRevokeConsent: (patientId: number) =>
    post<{ patient_id: string; state: string }>(`/api/clinical/patients/${patientId}/consent/revoke`, {}),
  clinicalReport: (patientId: number) =>
    get<Record<string, unknown>>(`/api/clinical/patients/${patientId}/report`),
  clinicalPatchReport: (patientId: number, body: { lab_notes?: string; review_status?: string }) =>
    patch<Record<string, unknown>>(`/api/clinical/patients/${patientId}/report`, body),
  clinicalSaveWorkupResult: (patientId: number, result: WorkupResult) =>
    post<{ ok: boolean; workup: WorkupSnapshot }>(
      `/api/clinical/patients/${patientId}/workup-result`,
      result,
    ),
  clinicalWorkupResult: (patientId: number) =>
    get<WorkupSnapshot>(`/api/clinical/patients/${patientId}/workup-result`),
  clinicalLongitudinal: (patientId: number) =>
    get<{
      patient_id: number;
      series: Array<{
        variant_key: string;
        gene: string | null;
        observation_count: number;
        trajectory_available: boolean;
        points: Array<{
          observation_date: number;
          allele_fraction: number | null;
          filename: string | null;
        }>;
      }>;
      observation_count: number;
      trajectory_available: boolean;
      message: string | null;
      outcome: { supported: boolean; message: string; note: string };
    }>(`/api/clinical/patients/${patientId}/longitudinal`),
  clinicalCandidates: (patientId: number) =>
    get<{
      kind: string;
      disclaimer: string;
      items: Array<Record<string, unknown>>;
      genes?: string[];
      reason?: string;
    }>(`/api/clinical/patients/${patientId}/candidates`),
  clinicalCurated: (gene: string) =>
    get<{
      kind: string;
      disclaimer: string;
      items: Array<{
        gene: string;
        chrom: string;
        pos: number;
        ref: string;
        alt: string;
        label?: string;
        review_status?: string;
        disclaimer: string;
        source_type: string;
      }>;
      reason?: string;
    }>(`/api/clinical/curated?gene=${encodeURIComponent(gene)}`),
  clinicalInterpretCurated: (body: {
    chromosome: string;
    position: number;
    reference: string;
    alternate: string;
    gene?: string;
    patient_id?: number;
  }) => post<Record<string, unknown>>("/api/clinical/curated/interpret", body),
  mlHealth: () => get<Record<string, unknown>>("/api/ml/health"),
};

export interface ClinicalPatient {
  id: number;
  uuid?: string;
  identifier: string;
  email?: string | null;
  full_name?: string | null;
  account_status?: string;
  user_id?: number | null;
  age: number | null;
  sex: string | null;
  diagnosis: string | null;
  presenting_complaint: string | null;
  consent_confirmed: number;
  created_at: number;
}

export interface ClinicalUpload {
  id: number;
  patient_id: number | null;
  filename: string;
  file_type: string;
  file_size: number;
  sha256: string;
  parsing_status: string;
  parsing_error: string | null;
  variant_count: number;
  uploaded_at: number;
}

export interface ClinicalVariant {
  id: number;
  vcf_upload_id: number;
  chromosome: string | null;
  position: number | null;
  reference: string | null;
  alternate: string | null;
  gene: string | null;
  hgvs_c: string | null;
  hgvs_p: string | null;
  normalized_variant: string | null;
  source_type?: string;
}

export interface WorkupSnapshot {
  id: number;
  patient_id: number;
  gene: string | null;
  hgvs_c: string | null;
  variant_label: string | null;
  acmg_classification: string | null;
  ml_top_class: string | null;
  final_classification: string | null;
  reconciliation_status: string | null;
  created_at: number;
  payload: WorkupResult;
}

export interface ClinicalBundle {
  patient: ClinicalPatient;
  phenotypes: { phenotype: string }[];
  family_history: { condition: string }[];
  medications: { medication: string }[];
  uploads: ClinicalUpload[];
  reconciliations: { final_classification: string; confidence?: string }[];
  workup?: WorkupSnapshot | null;
}

export async function uploadClinicalFile(file: File, patientId?: number | null): Promise<ClinicalUpload> {
  const body = new FormData();
  body.append("file", file);
  if (patientId) body.append("patient_id", String(patientId));
  const res = await fetch(`${API}/api/clinical/uploads`, {
    method: "POST",
    headers: await apiHeaders(),
    body,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const err = await res.json();
      detail = typeof err?.detail === "string" ? err.detail : "";
    } catch {
      /* ignore */
    }
    throw new Error(detail || `upload failed (${res.status})`);
  }
  return res.json();
}
