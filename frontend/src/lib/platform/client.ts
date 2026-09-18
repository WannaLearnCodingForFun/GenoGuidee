import { apiGet, apiPost } from "@/lib/api";
import type { Role } from "@/lib/useAccount";
import type {
  ACMGEvaluateResult,
  ACMGSimulation,
  DiseaseRankItem,
  DriftSnapshot,
  EvidenceRadar,
  GeneRankItem,
  InheritanceResult,
  InterpretationDiff,
  InterpretationVersion,
  ModelOODResult,
  PhenotypeMatchResult,
  PhenotypeNormalize,
  PhenotypeRanking,
  PlatformGraph,
  ReanalysisChange,
  ReanalysisCheck,
  ReanalysisJob,
  ReanalysisRun,
} from "@/lib/platform/types";

export function xRoleFor(role: Role): string {
  if (role === "lab_technician") return "LAB_CLINICIAN";
  if (role === "doctor") return "DOCTOR";
  if (role === "patient") return "PATIENT";
  return "RESEARCHER";
}

function hdr(role?: Role): Record<string, string> {
  return { "X-Role": xRoleFor(role ?? "") };
}

export const platformApi = {
  flags: () => apiGet<{ flags: Record<string, boolean> }>("/api/v1/platform/flags"),

  radar: (body: Record<string, unknown>) =>
    apiPost<EvidenceRadar>("/api/v1/evidence/radar", body),

  graph: (seed: string) =>
    apiGet<PlatformGraph>(`/api/v1/graph?seed=${encodeURIComponent(seed)}`),

  addEdge: (body: Record<string, unknown>) =>
    apiPost<Record<string, unknown>>("/api/v1/evidence/graph/edge", body),

  explain: (body: Record<string, unknown>) =>
    apiPost<{
      summary: string;
      claims: { text: string; evidence_ids: string[] }[];
      unsupported_claims: string[];
      confidence: string;
      llm_used: boolean;
      prescribes_treatment: boolean;
      sets_acmg: boolean;
    }>("/api/v1/evidence/explain", body),

  timeline: (variantId: string) =>
    apiGet<{ variant_id: string; events: Record<string, unknown>[] }>(
      `/api/v1/evidence/timeline/${encodeURIComponent(variantId)}`,
    ),

  history: (id: string) =>
    apiGet<{ interpretation_id: string; versions: InterpretationVersion[] }>(
      `/api/v1/interpretations/${encodeURIComponent(id)}/history`,
    ),

  diff: (id: string, a: number, b: number) =>
    apiGet<InterpretationDiff>(
      `/api/v1/interpretations/${encodeURIComponent(id)}/diff/${a}/${b}`,
    ),

  reanalysisCheck: () => apiPost<ReanalysisCheck>("/api/v1/reanalysis/check", {}),
  reanalysisRun: () => apiPost<ReanalysisRun>("/api/v1/reanalysis/run", {}),
  reanalysisJob: (id: string) =>
    apiGet<ReanalysisJob>(`/api/v1/reanalysis/jobs/${encodeURIComponent(id)}`),
  reanalysisChanges: () =>
    apiGet<{ changes: ReanalysisChange[] }>("/api/v1/reanalysis/changes"),

  watchlistAdd: (body: { variant_id?: string; patient_id?: number; case_id?: string }, role?: Role) =>
    apiPost<Record<string, unknown>>("/api/v1/watchlist", body, hdr(role)),
  watchlistList: (role?: Role) =>
    apiGet<{ items: Record<string, unknown>[] }>("/api/v1/watchlist", hdr(role)),
  watchlistTriggers: () =>
    apiGet<{ triggers: Record<string, unknown>[] }>("/api/v1/watchlist/triggers"),

  phenotypesNormalize: (terms: unknown[]) =>
    apiPost<PhenotypeNormalize>("/api/v1/phenotypes/normalize", { terms }),
  phenotypesMatch: (terms: unknown[], gene?: string) =>
    apiPost<PhenotypeMatchResult>("/api/v1/phenotypes/match", { terms, gene }),
  phenotypesRankGenes: (terms: unknown[], top = 10) =>
    apiPost<PhenotypeRanking<GeneRankItem>>("/api/v1/phenotypes/rank-genes", { terms, top }),
  phenotypesRankDiseases: (terms: unknown[], top = 10) =>
    apiPost<PhenotypeRanking<DiseaseRankItem>>("/api/v1/phenotypes/rank-diseases", { terms, top }),
  phenotypesEvolution: (body: Record<string, unknown>, role?: Role) =>
    apiPost<Record<string, unknown>>("/api/v1/phenotypes/evolution", body, hdr(role)),
  phenotypesEvolutionGet: (patientId: number, role?: Role) =>
    apiGet<Record<string, unknown>>(`/api/v1/phenotypes/evolution/${patientId}`, hdr(role)),

  inheritanceSolve: (body: Record<string, unknown>) =>
    apiPost<InheritanceResult>("/api/v1/inheritance/solve", body),

  acmgEvaluate: (body: Record<string, unknown> = {}) =>
    apiPost<ACMGEvaluateResult>("/api/v1/acmg/evaluate", body),
  acmgRules: () =>
    apiGet<{
      rule_version: string;
      criteria: { id: string; name: string; category: string; default_strength: string; enabled_by_default: boolean }[];
      specifications: string[];
    }>("/api/v1/acmg/rules"),
  acmgSimulate: (official: Record<string, unknown>, modifications: Record<string, unknown>[]) =>
    apiPost<ACMGSimulation>("/api/v1/acmg/simulate", { official, modifications }),

  curation: (body: Record<string, unknown>, role?: Role) =>
    apiPost<Record<string, unknown>>("/api/v1/curation", body, hdr(role)),
  curationEvents: (id: string) =>
    apiGet<{ events: Record<string, unknown>[] }>(
      `/api/v1/curation/${encodeURIComponent(id)}/events`,
    ),

  createCase: (patientId?: number, role?: Role) =>
    apiPost<{ case_id: string; patient_id: number | null }>(
      "/api/v1/cases",
      { patient_id: patientId ?? null },
      hdr(role),
    ),
  phenopacketImport: (phenopacket: Record<string, unknown>, caseId?: string) =>
    apiPost<{ imported: boolean; parsed: Record<string, unknown> }>(
      "/api/v1/phenopackets/import",
      { phenopacket, case_id: caseId },
    ),
  phenopacketExport: (caseId: string) =>
    apiGet<Record<string, unknown>>(`/api/v1/cases/${encodeURIComponent(caseId)}/phenopacket`),

  monitorLatest: () => apiGet<DriftSnapshot>("/api/v1/model-monitoring"),
  monitorSnapshot: (predictions: Record<string, unknown>[], prior?: Record<string, number>) =>
    apiPost<DriftSnapshot>("/api/v1/model-monitoring/snapshot", {
      predictions,
      training_prior: prior,
    }),
  monitorOod: (ml: Record<string, unknown>, acmg?: string) =>
    apiPost<ModelOODResult>("/api/v1/model-monitoring/ood", {
      ml,
      acmg_classification: acmg,
    }),
};
