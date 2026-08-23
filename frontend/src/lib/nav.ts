import type { Role } from "@/lib/useAccount";

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
    ALL.therapy,
    ALL.knowledgeGraph,
    ALL.provenance,
    ALL.upload,
  ],
  patient: [ALL.dashboard, ALL.patientContext, ALL.upload, ALL.provenance],
  lab_technician: [
    ALL.dashboard,
    ALL.variantLab,
    ALL.patientContext,
    ALL.provenance,
    ALL.upload,
  ],
  "": [ALL.dashboard],
};

export function allowedPathsForRole(role: Role): string[] {
  return (NAV_BY_ROLE[role] ?? NAV_BY_ROLE[""]).map((n) => n.href);
}

export function pathAllowedForRole(role: Role, path: string): boolean {
  return allowedPathsForRole(role).some((p) => path === p || path.startsWith(`${p}/`));
}
