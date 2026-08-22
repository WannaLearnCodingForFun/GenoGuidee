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
 * doctor: everything.
 * patient: dashboard, upload, and their own provenance — NOT variant-lab or
 *   therapy ranking (raw classifications/drug rankings are not shown to
 *   patients unmediated; this mirrors a clinical-safety norm, not just a nav
 *   preference).
 * lab_technician: dashboard + upload only, scoped to lab_orders assigned to
 *   them — NOT clinical-workup, NOT therapy. (Knowledge graph/patient context/
 *   variant-lab are clinician tools; a technician's job is limited to
 *   processing an assigned order, so they're excluded too pending explicit
 *   confirmation of a broader technician scope.)
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
  patient: [ALL.dashboard, ALL.upload, ALL.provenance],
  lab_technician: [ALL.dashboard, ALL.upload],
  "": [ALL.dashboard],
};

export function allowedPathsForRole(role: Role): string[] {
  return (NAV_BY_ROLE[role] ?? NAV_BY_ROLE.doctor).map((n) => n.href);
}
