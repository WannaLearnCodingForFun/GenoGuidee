"""Synthetic longitudinal fixtures. Clearly marked. Not clinical data."""
from __future__ import annotations

import json
import time
from typing import Any

from .. import clinical_db as DB
from .trajectory_score import variant_trajectory_score
from .variant_normalize import canonical_variant_id

SYNTHETIC_EMAIL = "synthetic.longitudinal@genoguide.demo"
SAMPLE = "SYNTHETIC-DEMO"

PREFERRED_IDS = ("PAT-2026-000002", "PAT-2026-000003")

_DATES_A = [
    time.mktime(time.strptime("2026-01-15", "%Y-%m-%d")),
    time.mktime(time.strptime("2026-03-15", "%Y-%m-%d")),
    time.mktime(time.strptime("2026-05-15", "%Y-%m-%d")),
    time.mktime(time.strptime("2026-07-15", "%Y-%m-%d")),
]
_DATES_B = [
    time.mktime(time.strptime("2026-02-10", "%Y-%m-%d")),
    time.mktime(time.strptime("2026-04-10", "%Y-%m-%d")),
    time.mktime(time.strptime("2026-06-10", "%Y-%m-%d")),
    time.mktime(time.strptime("2026-08-10", "%Y-%m-%d")),
]

# Worsening profile (breast / BRCA1).
WORSENING = [
    {
        "gene": "BRCA1", "hgvs": "c.5266dupC", "chromosome": "17",
        "position": 43051117, "reference": "C", "alternate": "CC",
        "story": "persistent + worsening",
        "vafs": [0.22, 0.31, 0.40, 0.48],
        "classes": ["Likely Pathogenic", "Likely Pathogenic", "Pathogenic", "Pathogenic"],
        "p_hat": [0.71, 0.78, 0.86, 0.91],
        "present": [True, True, True, True],
    },
    {
        "gene": "TP53", "hgvs": "c.524G>A", "chromosome": "17",
        "position": 7675088, "reference": "C", "alternate": "T",
        "story": "newly detected then reclassified",
        "vafs": [None, None, 0.07, 0.13],
        "classes": [None, None, "VUS", "Likely Pathogenic"],
        "p_hat": [None, None, 0.44, 0.68],
        "present": [False, False, True, True],
    },
    {
        "gene": "PALB2", "hgvs": "c.1592del", "chromosome": "16",
        "position": 23632683, "reference": "CT", "alternate": "C",
        "story": "stable VUS",
        "vafs": [0.48, 0.49, 0.47, 0.50],
        "classes": ["VUS", "VUS", "VUS", "VUS"],
        "p_hat": [0.36, 0.37, 0.35, 0.38],
        "present": [True, True, True, True],
    },
]

# Improving profile (brain / FAS). VAF falling, class more benign.
IMPROVING = [
    {
        "gene": "FAS", "hgvs": "c.651+2T>A", "chromosome": "10",
        "position": 89008996, "reference": "A", "alternate": "T",
        "story": "decreasing VAF + milder class",
        "vafs": [0.36, 0.24, 0.13, 0.05],
        "classes": ["VUS", "VUS", "Likely Benign", "Likely Benign"],
        "p_hat": [0.48, 0.32, 0.14, 0.06],
        "present": [True, True, True, True],
    },
    {
        "gene": "IDH1", "hgvs": "c.395G>A", "chromosome": "2",
        "position": 208248388, "reference": "C", "alternate": "T",
        "story": "not detected later",
        "vafs": [0.16, 0.09, None, None],
        "classes": ["Likely Pathogenic", "VUS", None, None],
        "p_hat": [0.61, 0.38, None, None],
        "present": [True, True, False, False],
    },
    {
        "gene": "TP53", "hgvs": "c.743G>A", "chromosome": "17",
        "position": 7674220, "reference": "C", "alternate": "T",
        "story": "falling VAF",
        "vafs": [0.14, 0.09, 0.05, 0.03],
        "classes": ["VUS", "VUS", "Likely Benign", "Likely Benign"],
        "p_hat": [0.40, 0.28, 0.14, 0.08],
        "present": [True, True, True, True],
    },
]

# Used when the two live patients are missing (tests / empty DB).
_FALLBACK = WORSENING + [
    {
        "gene": "EGFR", "hgvs": "c.2369C>T", "chromosome": "7",
        "position": 55181378, "reference": "C", "alternate": "T",
        "story": "newly detected",
        "vafs": [None, None, 0.08, 0.14],
        "classes": [None, None, "VUS", "Likely Pathogenic"],
        "p_hat": [None, None, 0.41, 0.67],
        "present": [False, False, True, True],
    },
    {
        "gene": "CFTR", "hgvs": "c.1521_1523del", "chromosome": "7",
        "position": 117559590, "reference": "ATCT", "alternate": "A",
        "story": "decreasing VAF",
        "vafs": [0.41, 0.28, 0.17, 0.09],
        "classes": ["Pathogenic", "Pathogenic", "Pathogenic", "Pathogenic"],
        "p_hat": [0.86, 0.85, 0.84, 0.83],
        "present": [True, True, True, True],
    },
]


def seed_longitudinal_demo(created_by: int) -> dict[str, Any]:
    """Attach 4-test synthetic snapshots to two patients when they exist."""
    seeded: list[dict[str, Any]] = []
    preferred = []
    for ident in PREFERRED_IDS:
        row = DB.get_patient_by_identifier(ident)
        if row:
            preferred.append(row)
    if len(preferred) >= 2:
        plans = [
            (preferred[0], WORSENING, _DATES_A, "worsening BRCA-spectrum demo"),
            (preferred[1], IMPROVING, _DATES_B, "improving FAS-spectrum demo"),
        ]
    else:
        synthetic = _ensure_synthetic_patient(created_by)
        plans = [(synthetic, _FALLBACK, _DATES_A, "synthetic multi-test demonstration")]
        for row in preferred:
            if int(row["id"]) != int(synthetic["id"]):
                plans.append((row, IMPROVING, _DATES_B, "improving FAS-spectrum demo"))

    for patient, variants, dates, label in plans:
        pid = int(patient["id"])
        DB.assign_user(pid, created_by, "doctor")
        _wipe_synthetic_only(pid)
        _write_tests(pid, created_by, variants, dates)
        seeded.append({
            **DB.public_patient(DB.get_patient(pid)),
            "demo_story": label,
            "snapshots": DB.list_genomic_snapshots(pid),
        })

    return {
        "synthetic": True,
        "patient": seeded[0],
        "patients": seeded,
        "note": (
            "Synthetic four-test observations were attached for demonstration. "
            "They are marked SYNTHETIC-DEMO and are not real sequencing results."
        ),
    }


def _ensure_synthetic_patient(created_by: int) -> dict[str, Any]:
    existing = DB.get_user_by_email(SYNTHETIC_EMAIL)
    if existing:
        patient = DB.patient_for_user(existing)
        if patient:
            return patient
        user = existing
    else:
        user = DB.create_user(
            SYNTHETIC_EMAIL, "unused-synthetic", "patient", "Synthetic Longitudinal Demo",
        )
    return DB.create_patient(
        created_by=created_by,
        user_id=user["id"],
        age=42,
        sex="F",
        diagnosis="Synthetic multi-test demonstration (not a real person)",
        presenting_complaint="DEMO — longitudinal fixture",
        consent_confirmed=True,
        email=SYNTHETIC_EMAIL,
        full_name="Synthetic Longitudinal Demo",
    )


def _write_tests(
    patient_id: int,
    created_by: int,
    variants: list[dict[str, Any]],
    dates: list[float],
) -> None:
    for i, ts in enumerate(dates):
        upload = DB.create_upload(
            patient_id=patient_id,
            uploaded_by=created_by,
            filename=f"synthetic_test_{i + 1}.vcf",
            file_type="vcf",
            file_size=128,
            sha256=f"synthetic-{patient_id}-{i + 1}-{int(ts)}",
            storage_path=f"synthetic/{patient_id}/test{i + 1}.vcf",
            parsing_status="PARSED",
        )
        DB.update_upload(
            int(upload["id"]),
            variant_count=sum(1 for v in variants if v["present"][i]),
            analysis_status="COMPLETED",
        )
        snap = DB.get_or_create_snapshot_for_upload(int(upload["id"]), patient_id)
        con = DB.connect()
        try:
            con.execute(
                "UPDATE genomic_test_snapshots SET test_date=?, sample_identifier=?, status=? WHERE id=?",
                (ts, SAMPLE, "ANALYZED", snap["id"]),
            )
            con.commit()
        finally:
            con.close()
        for spec in variants:
            if not spec["present"][i]:
                continue
            canon = canonical_variant_id(
                chromosome=spec["chromosome"], position=spec["position"],
                reference=spec["reference"], alternate=spec["alternate"],
            )
            rec = {
                "chromosome": spec["chromosome"], "position": spec["position"],
                "reference": spec["reference"], "alternate": spec["alternate"],
                "genome_build": "GRCh38", "gene": spec["gene"],
                "hgvs_c": spec["hgvs"], "normalized_variant": canon,
                "source_type": "UPLOADED_VCF",
            }
            vid = DB.insert_variant(int(upload["id"]), rec)
            p_hat = spec["p_hat"][i]
            cls = spec["classes"][i]
            vaf = spec["vafs"][i]
            scored = variant_trajectory_score(
                pathogenicity_probability=p_hat,
                acmg_classification=cls,
                vaf=vaf,
                vaf_slope=None,
                detection_rate=1.0,
                confidence=0.7,
            )
            extra = {
                "canonical_variant_id": canon,
                "chromosome": spec["chromosome"],
                "position": spec["position"],
                "reference": spec["reference"],
                "alternate": spec["alternate"],
                "hgvs": spec["hgvs"],
                "gene": spec["gene"],
                "allele_frequency": vaf,
                "detected": True,
            }
            oid = DB.insert_observation(
                patient_id=patient_id,
                variant_id=vid,
                source_file_id=int(upload["id"]),
                observation_date=ts,
                allele_fraction=vaf,
                source_dataset="SYNTHETIC_DEMO",
                snapshot_id=int(snap["id"]),
                extra=extra,
            )
            con = DB.connect()
            try:
                con.execute(
                    """UPDATE variant_observations SET
                       pathogenicity_probability=?, likely_pathogenic_probability=?,
                       vus_probability=?, likely_benign_probability=?, benign_probability=?,
                       acmg_classification=?, confidence=?, clinical_significance=?,
                       trajectory_score=?, trajectory_components=?,
                       model_name=?, model_version=?, feature_version=?,
                       training_dataset_version=?, inference_timestamp=?
                       WHERE id=?""",
                    (
                        p_hat,
                        max(0.0, (1 - (p_hat or 0)) * 0.35),
                        max(0.0, (1 - (p_hat or 0)) * 0.40),
                        max(0.0, (1 - (p_hat or 0)) * 0.15),
                        max(0.0, (1 - (p_hat or 0)) * 0.10),
                        cls, 0.7, cls,
                        scored["variant_trajectory_score"],
                        json.dumps(scored["components"]),
                        "synthetic-demo", "demo-0", "demo-features",
                        "synthetic", ts, oid,
                    ),
                )
                con.commit()
            finally:
                con.close()
        DB.refresh_snapshot_scores(int(snap["id"]))


def _wipe_synthetic_only(patient_id: int) -> None:
    """Remove only SYNTHETIC-DEMO rows. Real uploads stay."""
    con = DB.connect()
    try:
        upload_ids = [
            r[0] for r in con.execute(
                """SELECT id FROM vcf_uploads
                   WHERE patient_id=? AND (filename LIKE 'synthetic_test_%' OR sha256 LIKE 'synthetic-%')""",
                (patient_id,),
            ).fetchall()
        ]
        snap_ids = [
            r[0] for r in con.execute(
                "SELECT id FROM genomic_test_snapshots WHERE patient_id=? AND sample_identifier=?",
                (patient_id, SAMPLE),
            ).fetchall()
        ]
        if snap_ids:
            ph = ",".join("?" * len(snap_ids))
            con.execute(
                f"DELETE FROM variant_observations WHERE snapshot_id IN ({ph})",
                snap_ids,
            )
            con.execute(
                f"DELETE FROM genomic_test_snapshots WHERE id IN ({ph})",
                snap_ids,
            )
        con.execute(
            "DELETE FROM variant_observations WHERE patient_id=? AND source_dataset=?",
            (patient_id, "SYNTHETIC_DEMO"),
        )
        if upload_ids:
            ph = ",".join("?" * len(upload_ids))
            con.execute(f"DELETE FROM variants WHERE vcf_upload_id IN ({ph})", upload_ids)
            con.execute(f"DELETE FROM vcf_uploads WHERE id IN ({ph})", upload_ids)
        con.execute("DELETE FROM patient_trajectory_summaries WHERE patient_id=?", (patient_id,))
        con.commit()
    finally:
        con.close()
