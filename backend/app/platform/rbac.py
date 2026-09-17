"""Platform RBAC. Clinical users.role CHECK is unchanged; extra roles live in user_platform_roles."""
from __future__ import annotations

from typing import Optional

CLINICAL_TO_PLATFORM = {
    "doctor": "DOCTOR",
    "patient": "PATIENT",
    "lab_technician": "LAB_CLINICIAN",
}

PLATFORM_ROLES = {
    "PATIENT", "DOCTOR", "LAB_CLINICIAN", "GENETIC_COUNSELOR", "RESEARCHER", "ADMIN",
}

PERMISSIONS: dict[str, set[str]] = {
    "PATIENT": {"read:own"},
    "DOCTOR": {"read:own", "read:assigned", "interpret", "curate", "finalize", "watch"},
    "LAB_CLINICIAN": {"read:assigned", "interpret", "curate", "finalize", "watch", "vcf"},
    "GENETIC_COUNSELOR": {"read:assigned", "interpret", "curate", "watch"},
    "RESEARCHER": {"read:deidentified", "research"},
    "ADMIN": {"read:own", "read:assigned", "read:deidentified", "interpret",
              "curate", "finalize", "watch", "vcf", "research", "admin"},
}


def normalize_role(role: Optional[str]) -> str:
    if not role:
        return "RESEARCHER"
    r = role.strip()
    mapped = CLINICAL_TO_PLATFORM.get(r.lower())
    if mapped:
        return mapped
    up = r.upper().replace("-", "_")
    if up == "LAB_TECHNICIAN":
        return "LAB_CLINICIAN"
    if up not in PLATFORM_ROLES:
        return "RESEARCHER"
    return up


def has_perm(role: str, permission: str) -> bool:
    return permission in PERMISSIONS.get(normalize_role(role), set())


def can_finalize(role: str) -> bool:
    return has_perm(role, "finalize")


def can_see_identity(role: str) -> bool:
    return normalize_role(role) != "RESEARCHER"


def can_access_patient_role(role: str, *, owner: bool, assigned: bool) -> bool:
    r = normalize_role(role)
    if r == "ADMIN":
        return True
    if r == "LAB_CLINICIAN":
        return True
    if r == "RESEARCHER":
        return False  # identity path denied; use cohort APIs
    if r == "PATIENT":
        return owner
    if r in {"DOCTOR", "GENETIC_COUNSELOR"}:
        return assigned or owner
    return False
