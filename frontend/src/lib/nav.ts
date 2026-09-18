import type { Role } from "@/lib/useAccount";
import { platformNavForRole } from "@/lib/platformNav";

export interface NavItem {
  href: string;
  label: string;
}

const ALL: Record<string, NavItem> = {
  dashboard: { href: "/dashboard", label: "Overview" },
  upload: { href: "/upload", label: "Upload & Tracker" },
  clinicalWorkup: { href: "/clinical-workup", label: "Clinical Workup" },
  variantLab: { href: "/variant-lab", label: "Variant Lab" },
  patientContext: { href: "/patient-context", label: "Patient Context" },
  therapy: { href: "/therapy", label: "Therapy Ranking" },
  knowledgeGraph: { href: "/knowledge-graph", label: "Knowledge Graph" },
  provenance: { href: "/provenance", label: "Provenance" },
  genomicTimeline: { href: "/genomic-timeline", label: "Genomic Timeline" },
  modelEval: { href: "/model-evaluation", label: "Model Evaluation" },
};

/**
 * Phase B2 — per-role page visibility.
 *
 * doctor: full clinical workspace.
 * patient: own record, uploads, context (including longitudinal), provenance.
 *   Therapy ranking remains clinician-mediated.
 * lab_technician: all patients, uploads, variant lab, context, provenance.
 *   Cannot create patients or submit clinical workup.
 */
export const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  doctor: [
    ALL.dashboard,
    ALL.clinicalWorkup,
    ALL.variantLab,
    ALL.patientContext,
    ALL.genomicTimeline,
    ALL.therapy,
    ALL.knowledgeGraph,
    ALL.provenance,
    ALL.modelEval,
    ALL.upload,
  ],
  patient: [ALL.dashboard, ALL.patientContext, ALL.genomicTimeline, ALL.upload, ALL.provenance],
  lab_technician: [
    ALL.dashboard,
    ALL.variantLab,
    ALL.patientContext,
    ALL.genomicTimeline,
    ALL.provenance,
    ALL.modelEval,
    ALL.upload,
  ],
  "": [ALL.dashboard],
};

export function navItemsForRole(role: Role): NavItem[] {
  const base = NAV_BY_ROLE[role] ?? NAV_BY_ROLE[""];
  return [...base, ...platformNavForRole(role)];
}

export function allowedPathsForRole(role: Role): string[] {
  const extra = role === "doctor" || role === "lab_technician" ? ["/interpretations"] : [];
  return [...navItemsForRole(role).map((n) => n.href), ...extra];
}

export function pathAllowedForRole(role: Role, path: string): boolean {
  return allowedPathsForRole(role).some((p) => path === p || path.startsWith(`${p}/`));
}
