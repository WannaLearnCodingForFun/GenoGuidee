"""Persistent clinical store (SQLite). Not the synthetic demo dataset."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .config import BASE_DIR

_lock = threading.Lock()


def db_path() -> Path:
    override = os.environ.get("GENOGUIDE_CLINICAL_DB")
    return Path(override) if override else Path(BASE_DIR) / "clinical.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('doctor','patient','lab_technician')),
  full_name TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS patients (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT UNIQUE,
  identifier TEXT NOT NULL UNIQUE,
  user_id INTEGER REFERENCES users(id),
  created_by INTEGER REFERENCES users(id),
  email TEXT,
  full_name TEXT,
  account_status TEXT NOT NULL DEFAULT 'pending',
  age INTEGER,
  sex TEXT,
  diagnosis TEXT,
  presenting_complaint TEXT,
  consent_confirmed INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS patient_assignments (
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  user_id INTEGER NOT NULL REFERENCES users(id),
  role TEXT NOT NULL,
  assigned_at REAL,
  assigned_by INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  PRIMARY KEY (patient_id, user_id)
);
CREATE TABLE IF NOT EXISTS patient_invitations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  token_hash TEXT NOT NULL UNIQUE,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  used_at REAL,
  used_by INTEGER
);
CREATE TABLE IF NOT EXISTS patient_phenotypes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  phenotype TEXT NOT NULL,
  hpo_id TEXT,
  source TEXT NOT NULL DEFAULT 'intake',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS family_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  relationship TEXT,
  condition TEXT NOT NULL,
  age_at_diagnosis INTEGER,
  source TEXT NOT NULL DEFAULT 'intake',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS medications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  medication TEXT NOT NULL,
  dosage TEXT,
  frequency TEXT,
  pgx_note TEXT,
  source TEXT NOT NULL DEFAULT 'intake',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS vcf_uploads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER REFERENCES patients(id),
  uploaded_by INTEGER NOT NULL REFERENCES users(id),
  filename TEXT NOT NULL,
  file_type TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  sha256 TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  uploaded_at REAL NOT NULL,
  parsing_status TEXT NOT NULL,
  parsing_error TEXT,
  variant_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vcf_upload_id INTEGER NOT NULL REFERENCES vcf_uploads(id),
  chromosome TEXT,
  position INTEGER,
  reference TEXT,
  alternate TEXT,
  genome_build TEXT,
  gene TEXT,
  transcript TEXT,
  consequence TEXT,
  hgvs_c TEXT,
  hgvs_p TEXT,
  rsid TEXT,
  normalized_variant TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS variant_annotations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_id INTEGER NOT NULL REFERENCES variants(id),
  clinvar_significance TEXT,
  review_status TEXT,
  allele_frequency REAL,
  evidence_source TEXT,
  payload_json TEXT,
  fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ml_predictions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_id INTEGER NOT NULL REFERENCES variants(id),
  model_version TEXT NOT NULL,
  predicted_class TEXT NOT NULL,
  confidence REAL,
  calibration TEXT,
  payload_json TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS acmg_interpretations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_id INTEGER,
  patient_id INTEGER REFERENCES patients(id),
  classification TEXT NOT NULL,
  criteria_json TEXT NOT NULL,
  evidence_summary TEXT,
  rule_engine_version TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reconciliations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_id INTEGER,
  patient_id INTEGER REFERENCES patients(id),
  ml_classification TEXT,
  acmg_classification TEXT NOT NULL,
  final_classification TEXT NOT NULL,
  confidence TEXT,
  explanation TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_graph_entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  entity_key TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  label TEXT NOT NULL,
  sublabel TEXT,
  UNIQUE(patient_id, entity_key)
);
CREATE TABLE IF NOT EXISTS knowledge_graph_relationships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  source_key TEXT NOT NULL,
  target_key TEXT NOT NULL,
  relation TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS therapy_results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER REFERENCES patients(id),
  variant_id INTEGER,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS provenance_blocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  block_number INTEGER NOT NULL,
  previous_hash TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  block_hash TEXT NOT NULL,
  patient_id INTEGER,
  event_type TEXT NOT NULL,
  contract_name TEXT,
  function_name TEXT,
  payload_json TEXT NOT NULL,
  timestamp REAL NOT NULL,
  verification_status TEXT NOT NULL DEFAULT 'recorded'
);
CREATE TABLE IF NOT EXISTS reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER,
  variant_id INTEGER,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS workup_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  gene TEXT,
  hgvs_c TEXT,
  variant_label TEXT,
  acmg_classification TEXT,
  ml_top_class TEXT,
  final_classification TEXT,
  reconciliation_status TEXT,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS variant_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER NOT NULL REFERENCES patients(id),
  variant_id INTEGER REFERENCES variants(id),
  source_file_id INTEGER REFERENCES vcf_uploads(id),
  observation_date REAL NOT NULL,
  allele_fraction REAL,
  clinical_status TEXT,
  source_dataset TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS model_registry (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model_name TEXT NOT NULL,
  version TEXT NOT NULL,
  dataset TEXT,
  dataset_version TEXT,
  metrics_json TEXT,
  artifact_path TEXT,
  status TEXT NOT NULL DEFAULT 'registered',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER,
  patient_id INTEGER,
  action TEXT NOT NULL,
  resource TEXT NOT NULL,
  resource_id TEXT,
  timestamp REAL NOT NULL,
  metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_patients_created_by ON patients(created_by);
CREATE INDEX IF NOT EXISTS idx_patients_user ON patients(user_id);
CREATE INDEX IF NOT EXISTS idx_patients_created ON patients(created_at);
CREATE INDEX IF NOT EXISTS idx_uploads_patient ON vcf_uploads(patient_id);
CREATE INDEX IF NOT EXISTS idx_uploads_user ON vcf_uploads(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_uploads_sha ON vcf_uploads(sha256);
CREATE INDEX IF NOT EXISTS idx_uploads_at ON vcf_uploads(uploaded_at);
CREATE INDEX IF NOT EXISTS idx_variants_upload ON variants(vcf_upload_id);
CREATE INDEX IF NOT EXISTS idx_variants_created ON variants(created_at);
CREATE INDEX IF NOT EXISTS idx_ml_variant ON ml_predictions(variant_id);
CREATE INDEX IF NOT EXISTS idx_acmg_variant ON acmg_interpretations(variant_id);
CREATE INDEX IF NOT EXISTS idx_acmg_patient ON acmg_interpretations(patient_id);
CREATE INDEX IF NOT EXISTS idx_prov_patient ON provenance_blocks(patient_id);
CREATE INDEX IF NOT EXISTS idx_prov_hash ON provenance_blocks(block_hash);
CREATE INDEX IF NOT EXISTS idx_audit_patient ON audit_logs(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_workup_patient ON workup_snapshots(patient_id);
"""


def _table_cols(con: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_col(con: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name not in _table_cols(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _migrate_columns(con: sqlite3.Connection) -> None:
    _add_col(con, "patients", "uuid", "TEXT")
    _add_col(con, "patients", "email", "TEXT")
    _add_col(con, "patients", "full_name", "TEXT")
    _add_col(con, "patients", "account_status", "TEXT DEFAULT 'pending'")
    _add_col(con, "patient_assignments", "assigned_at", "REAL")
    _add_col(con, "patient_assignments", "assigned_by", "INTEGER")
    _add_col(con, "patient_assignments", "status", "TEXT DEFAULT 'active'")
    _add_col(con, "vcf_uploads", "analysis_status", "TEXT")
    _add_col(con, "vcf_uploads", "uploaded_by_role", "TEXT")
    _add_col(con, "variants", "source_type", "TEXT DEFAULT 'UPLOADED_VCF'")
    _add_col(con, "variants", "patient_id", "INTEGER")
    missing = con.execute("SELECT id FROM patients WHERE uuid IS NULL OR uuid=''").fetchall()
    for (pid,) in missing:
        con.execute("UPDATE patients SET uuid=? WHERE id=?", (str(uuid.uuid4()), pid))
    con.execute(
        """UPDATE patients SET account_status=CASE
             WHEN user_id IS NOT NULL THEN 'active'
             WHEN account_status IS NULL OR account_status='' THEN 'pending'
             ELSE account_status END"""
    )
    con.execute(
        """UPDATE variants SET patient_id=(
             SELECT u.patient_id FROM vcf_uploads u WHERE u.id=variants.vcf_upload_id
           ) WHERE patient_id IS NULL"""
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_patients_uuid ON patients(uuid)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_invites_hash ON patient_invitations(token_hash)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_invites_patient ON patient_invitations(patient_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_assign_doctor ON patient_assignments(user_id, patient_id)")
    con.executescript(
        """CREATE TABLE IF NOT EXISTS workup_snapshots (
             id INTEGER PRIMARY KEY AUTOINCREMENT,
             patient_id INTEGER NOT NULL REFERENCES patients(id),
             gene TEXT,
             hgvs_c TEXT,
             variant_label TEXT,
             acmg_classification TEXT,
             ml_top_class TEXT,
             final_classification TEXT,
             reconciliation_status TEXT,
             payload_json TEXT NOT NULL,
             created_at REAL NOT NULL
           );
           CREATE INDEX IF NOT EXISTS idx_workup_patient ON workup_snapshots(patient_id);"""
    )


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init() -> None:
    with _lock:
        con = connect()
        try:
            con.executescript(SCHEMA)
            _migrate_columns(con)
            con.commit()
        finally:
            con.close()
    _seed_model_registry()


def _seed_model_registry() -> None:
    """Register local model artifacts. Never invent metrics."""
    registry_dir = Path(__file__).resolve().parents[2] / "models" / "registry"
    if not registry_dir.is_dir():
        return
    con = connect()
    try:
        for path in sorted(registry_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            name = str(data.get("model_id") or data.get("model_name") or path.stem)
            version = str(data.get("version") or data.get("model_id") or "unknown")
            exists = con.execute(
                "SELECT 1 FROM model_registry WHERE model_name=? AND version=?",
                (name, version),
            ).fetchone()
            if exists:
                continue
            training = data.get("training_dataset") or {}
            metrics = data.get("metrics") or data.get("metrics_gene_disjoint_test") or {}
            con.execute(
                """INSERT INTO model_registry (model_name, version, dataset, dataset_version,
                   metrics_json, artifact_path, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    name,
                    version,
                    training.get("path") if isinstance(training, dict) else data.get("dataset"),
                    data.get("dataset_version"),
                    json.dumps(metrics, default=str),
                    data.get("artifact") or data.get("artifact_path"),
                    "registered",
                    _now(),
                ),
            )
        con.commit()
    finally:
        con.close()


def _now() -> float:
    return time.time()


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(r) if r is not None else None


def next_patient_identifier() -> str:
    year = time.strftime("%Y")
    con = connect()
    try:
        row = con.execute(
            "SELECT identifier FROM patients WHERE identifier LIKE ? ORDER BY id DESC LIMIT 1",
            (f"PAT-{year}-%",),
        ).fetchone()
        n = 1
        if row:
            try:
                n = int(str(row[0]).rsplit("-", 1)[-1]) + 1
            except ValueError:
                n = int(con.execute("SELECT COUNT(*) FROM patients").fetchone()[0]) + 1
        ident = f"PAT-{year}-{n:06d}"
        while con.execute("SELECT 1 FROM patients WHERE identifier=?", (ident,)).fetchone():
            n += 1
            ident = f"PAT-{year}-{n:06d}"
        return ident
    finally:
        con.close()


def create_user(email: str, password_hash: str, role: str, full_name: str) -> dict[str, Any]:
    ts = _now()
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO users (email, password_hash, role, full_name, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (email.lower().strip(), password_hash, role, full_name.strip(), ts, ts),
        )
        con.commit()
        return get_user(cur.lastrowid)  # type: ignore[arg-type]
    finally:
        con.close()


def get_user(user_id: int) -> dict[str, Any]:
    con = connect()
    try:
        row = _row(con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())
        if not row:
            raise KeyError(user_id)
        return row
    finally:
        con.close()


def get_user_by_email(email: str) -> dict[str, Any] | None:
    con = connect()
    try:
        return _row(con.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone())
    finally:
        con.close()


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    return {k: row[k] for k in ("id", "email", "role", "full_name", "created_at") if k in row}


def create_patient(*, created_by: int, user_id: int | None, age, sex, diagnosis,
                   presenting_complaint, consent_confirmed: bool,
                   email: str | None = None, full_name: str | None = None) -> dict[str, Any]:
    ident = next_patient_identifier()
    ts = _now()
    status = "active" if user_id else "pending"
    con = connect()
    try:
        cur = con.execute(
            """INSERT INTO patients (uuid, identifier, user_id, created_by, email, full_name,
               account_status, age, sex, diagnosis, presenting_complaint, consent_confirmed,
               created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), ident, user_id, created_by,
             (email or "").strip().lower() or None, full_name,
             status, age, sex, diagnosis, presenting_complaint,
             1 if consent_confirmed else 0, ts, ts),
        )
        pid = cur.lastrowid
        if created_by and created_by != user_id:
            con.execute(
                """INSERT OR IGNORE INTO patient_assignments
                   (patient_id, user_id, role, assigned_at, assigned_by, status)
                   VALUES (?,?,?,?,?,?)""",
                (pid, created_by, "doctor", ts, created_by, "active"),
            )
        if user_id:
            con.execute(
                """INSERT OR IGNORE INTO patient_assignments
                   (patient_id, user_id, role, assigned_at, assigned_by, status)
                   VALUES (?,?,?,?,?,?)""",
                (pid, user_id, "patient", ts, created_by, "active"),
            )
        con.commit()
        return get_patient(pid)  # type: ignore[arg-type]
    finally:
        con.close()


def get_patient(patient_id: int) -> dict[str, Any]:
    con = connect()
    try:
        row = _row(con.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone())
        if not row:
            raise KeyError(patient_id)
        return row
    finally:
        con.close()


def get_patient_by_uuid(value: str) -> dict[str, Any] | None:
    con = connect()
    try:
        return _row(con.execute("SELECT * FROM patients WHERE uuid=?", (value,)).fetchone())
    finally:
        con.close()


def get_patient_by_identifier(ident: str) -> dict[str, Any] | None:
    con = connect()
    try:
        return _row(con.execute("SELECT * FROM patients WHERE identifier=?", (ident,)).fetchone())
    finally:
        con.close()


def resolve_registered_patient(ident: str) -> dict[str, Any]:
    value = (ident or "").strip()
    if not value:
        raise KeyError("missing")
    row = get_patient_by_identifier(value) or get_patient_by_uuid(value)
    if not row:
        raise KeyError(value)
    if not row.get("user_id"):
        raise ValueError("unlinked")
    return row


def purge_stored_patient_identities() -> dict[str, int]:
    """Wipe patient records and patient-role users. Keeps doctor/lab accounts."""
    tables = (
        "audit_logs", "provenance_blocks", "workup_snapshots", "reports", "therapy_results",
        "knowledge_graph_relationships", "knowledge_graph_entities",
        "reconciliations", "acmg_interpretations", "ml_predictions",
        "variant_annotations", "variant_observations", "variants", "vcf_uploads",
        "medications", "family_history", "patient_phenotypes",
        "patient_invitations", "patient_assignments", "patients",
    )
    con = connect()
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        deleted: dict[str, int] = {}
        for table in tables:
            deleted[table] = int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            con.execute(f"DELETE FROM {table}")
        deleted["patient_users"] = int(
            con.execute("SELECT COUNT(*) FROM users WHERE role='patient'").fetchone()[0]
        )
        con.execute("DELETE FROM users WHERE role='patient'")
        con.commit()
        return deleted
    finally:
        con.close()


def can_access_patient(user: dict[str, Any], patient_id: int) -> bool:
    if user["role"] == "doctor":
        con = connect()
        try:
            row = con.execute(
                "SELECT 1 FROM patients WHERE id=? AND created_by=?",
                (patient_id, user["id"]),
            ).fetchone()
            if row:
                return True
            asg = con.execute(
                """SELECT 1 FROM patient_assignments
                   WHERE patient_id=? AND user_id=? AND COALESCE(status,'active')='active'""",
                (patient_id, user["id"]),
            ).fetchone()
            return bool(asg)
        finally:
            con.close()
    if user["role"] == "patient":
        con = connect()
        try:
            row = con.execute(
                "SELECT 1 FROM patients WHERE id=? AND user_id=?",
                (patient_id, user["id"]),
            ).fetchone()
            return bool(row)
        finally:
            con.close()
    if user["role"] == "lab_technician":
        con = connect()
        try:
            row = con.execute("SELECT 1 FROM patients WHERE id=?", (patient_id,)).fetchone()
            return bool(row)
        finally:
            con.close()
    return False


def list_patients_for(user: dict[str, Any]) -> list[dict[str, Any]]:
    con = connect()
    try:
        if user["role"] == "doctor":
            rows = con.execute(
                """SELECT DISTINCT p.* FROM patients p
                   LEFT JOIN patient_assignments a ON a.patient_id=p.id AND a.user_id=?
                   WHERE p.created_by=? OR a.user_id=?
                   ORDER BY p.created_at DESC""",
                (user["id"], user["id"], user["id"]),
            ).fetchall()
        elif user["role"] == "patient":
            rows = con.execute(
                "SELECT * FROM patients WHERE user_id=? ORDER BY created_at DESC",
                (user["id"],),
            ).fetchall()
        elif user["role"] == "lab_technician":
            rows = con.execute("SELECT * FROM patients ORDER BY created_at DESC").fetchall()
        else:
            rows = []
        return [dict(r) for r in rows]
    finally:
        con.close()


def replace_history(patient_id: int, *, phenotypes: list[str], prior_conditions: list[str],
                    medications: list[str], family_details: str | None, family_positive: bool) -> None:
    ts = _now()
    con = connect()
    try:
        con.execute("DELETE FROM patient_phenotypes WHERE patient_id=?", (patient_id,))
        con.execute("DELETE FROM medications WHERE patient_id=?", (patient_id,))
        con.execute("DELETE FROM family_history WHERE patient_id=?", (patient_id,))
        for p in phenotypes:
            con.execute(
                "INSERT INTO patient_phenotypes (patient_id, phenotype, source, created_at) VALUES (?,?,?,?)",
                (patient_id, p, "intake", ts),
            )
        for m in medications:
            con.execute(
                "INSERT INTO medications (patient_id, medication, source, created_at) VALUES (?,?,?,?)",
                (patient_id, m, "intake", ts),
            )
        if family_details:
            con.execute(
                """INSERT INTO family_history (patient_id, relationship, condition, source, created_at)
                   VALUES (?,?,?,?,?)""",
                (patient_id, "family" if family_positive else "unspecified", family_details, "intake", ts),
            )
        for c in prior_conditions:
            con.execute(
                """INSERT INTO family_history (patient_id, relationship, condition, source, created_at)
                   VALUES (?,?,?,?,?)""",
                (patient_id, "self", c, "intake", ts),
            )
        con.commit()
    finally:
        con.close()


def patient_bundle(patient_id: int) -> dict[str, Any]:
    con = connect()
    try:
        p = _row(con.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone())
        if not p:
            raise KeyError(patient_id)
        phen = [dict(r) for r in con.execute(
            "SELECT * FROM patient_phenotypes WHERE patient_id=?", (patient_id,)).fetchall()]
        fam = [dict(r) for r in con.execute(
            "SELECT * FROM family_history WHERE patient_id=?", (patient_id,)).fetchall()]
        meds = [dict(r) for r in con.execute(
            "SELECT * FROM medications WHERE patient_id=?", (patient_id,)).fetchall()]
        ups = [dict(r) for r in con.execute(
            "SELECT * FROM vcf_uploads WHERE patient_id=? ORDER BY uploaded_at DESC", (patient_id,)).fetchall()]
        recs = [dict(r) for r in con.execute(
            "SELECT * FROM reconciliations WHERE patient_id=? ORDER BY created_at DESC", (patient_id,)).fetchall()]
        bundle = {"patient": p, "phenotypes": phen, "family_history": fam,
                  "medications": meds, "uploads": ups, "reconciliations": recs}
    finally:
        con.close()
    bundle["workup"] = latest_workup_snapshot(patient_id)
    return bundle


def ensure_curated_catalog(user_id: int) -> int:
    """Shared catalog upload for ClinVar-derived candidate rows (not patient genotype)."""
    con = connect()
    try:
        row = con.execute(
            "SELECT id FROM vcf_uploads WHERE file_type='curated' ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            return int(row[0])
    finally:
        con.close()
    created = create_upload(
        patient_id=None,
        uploaded_by=user_id,
        filename="CURATED_DATASET",
        file_type="curated",
        file_size=0,
        sha256="curated-catalog",
        storage_path="",
        parsing_status="PARSED",
        variant_count=0,
        analysis_status="CURATED",
    )
    return int(created["id"])


def create_upload(**kwargs: Any) -> dict[str, Any]:
    con = connect()
    try:
        cur = con.execute(
            """INSERT INTO vcf_uploads (patient_id, uploaded_by, filename, file_type, file_size,
               sha256, storage_path, uploaded_at, parsing_status, parsing_error, variant_count)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (kwargs.get("patient_id"), kwargs["uploaded_by"], kwargs["filename"],
             kwargs["file_type"], kwargs["file_size"], kwargs["sha256"], kwargs["storage_path"],
             _now(), kwargs.get("parsing_status", "UPLOADED"), kwargs.get("parsing_error"),
             kwargs.get("variant_count", 0)),
        )
        con.commit()
        return dict(con.execute("SELECT * FROM vcf_uploads WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        con.close()


def update_upload(upload_id: int, **fields: Any) -> None:
    if not fields:
        return
    sets = ", ".join(f"{k}=?" for k in fields)
    con = connect()
    try:
        con.execute(f"UPDATE vcf_uploads SET {sets} WHERE id=?", (*fields.values(), upload_id))
        con.commit()
    finally:
        con.close()


def get_upload(upload_id: int) -> dict[str, Any]:
    con = connect()
    try:
        row = _row(con.execute("SELECT * FROM vcf_uploads WHERE id=?", (upload_id,)).fetchone())
        if not row:
            raise KeyError(upload_id)
        return row
    finally:
        con.close()


def list_uploads_for(user: dict[str, Any]) -> list[dict[str, Any]]:
    con = connect()
    try:
        if user["role"] == "doctor":
            rows = con.execute(
                """SELECT u.* FROM vcf_uploads u
                   LEFT JOIN patients p ON p.id=u.patient_id
                   WHERE u.uploaded_by=? OR p.created_by=?
                   ORDER BY u.uploaded_at DESC""",
                (user["id"], user["id"]),
            ).fetchall()
        elif user["role"] == "patient":
            rows = con.execute(
                """SELECT u.* FROM vcf_uploads u
                   JOIN patients p ON p.id=u.patient_id
                   WHERE p.user_id=?
                   UNION
                   SELECT u.* FROM vcf_uploads u WHERE u.uploaded_by=? AND u.patient_id IS NULL
                   ORDER BY uploaded_at DESC""",
                (user["id"], user["id"]),
            ).fetchall()
        elif user["role"] == "lab_technician":
            rows = con.execute("SELECT * FROM vcf_uploads ORDER BY uploaded_at DESC").fetchall()
        else:
            rows = []
        return [dict(r) for r in rows]
    finally:
        con.close()


def insert_variant(upload_id: int, rec: dict[str, Any]) -> int:
    con = connect()
    try:
        upload = con.execute("SELECT patient_id FROM vcf_uploads WHERE id=?", (upload_id,)).fetchone()
        patient_id = rec.get("patient_id") or (upload[0] if upload else None)
        cur = con.execute(
            """INSERT INTO variants (vcf_upload_id, chromosome, position, reference, alternate,
               genome_build, gene, transcript, consequence, hgvs_c, hgvs_p, rsid,
               normalized_variant, created_at, source_type, patient_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (upload_id, rec.get("chromosome"), rec.get("position"), rec.get("reference"),
             rec.get("alternate"), rec.get("genome_build"), rec.get("gene"), rec.get("transcript"),
             rec.get("consequence"), rec.get("hgvs_c"), rec.get("hgvs_p"), rec.get("rsid"),
             rec.get("normalized_variant"), _now(),
             rec.get("source_type") or "UPLOADED_VCF", patient_id),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def list_variants(upload_id: int | None = None, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    offset = max(0, (page - 1) * page_size)
    con = connect()
    try:
        if upload_id is None:
            total = con.execute("SELECT COUNT(*) FROM variants").fetchone()[0]
            rows = con.execute(
                "SELECT * FROM variants ORDER BY id DESC LIMIT ? OFFSET ?",
                (page_size, offset),
            ).fetchall()
        else:
            total = con.execute(
                "SELECT COUNT(*) FROM variants WHERE vcf_upload_id=?", (upload_id,)).fetchone()[0]
            rows = con.execute(
                "SELECT * FROM variants WHERE vcf_upload_id=? ORDER BY id LIMIT ? OFFSET ?",
                (upload_id, page_size, offset),
            ).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}
    finally:
        con.close()


def get_variant(variant_id: int) -> dict[str, Any]:
    con = connect()
    try:
        row = _row(con.execute("SELECT * FROM variants WHERE id=?", (variant_id,)).fetchone())
        if not row:
            raise KeyError(variant_id)
        return row
    finally:
        con.close()


def save_annotation(variant_id: int, payload: dict[str, Any]) -> None:
    con = connect()
    try:
        con.execute(
            """INSERT INTO variant_annotations (variant_id, clinvar_significance, review_status,
               allele_frequency, evidence_source, payload_json, fetched_at)
               VALUES (?,?,?,?,?,?,?)""",
            (variant_id, payload.get("clinvar_significance"), payload.get("review_status"),
             payload.get("allele_frequency"), payload.get("evidence_source"),
             json.dumps(payload), _now()),
        )
        con.commit()
    finally:
        con.close()


def save_ml(variant_id: int, pred: dict[str, Any]) -> None:
    con = connect()
    try:
        con.execute(
            """INSERT INTO ml_predictions (variant_id, model_version, predicted_class, confidence,
               calibration, payload_json, created_at) VALUES (?,?,?,?,?,?,?)""",
            (variant_id, pred.get("model_version") or "unknown", pred.get("top_class") or pred.get("predicted_class") or "not_run",
             pred.get("confidence"), pred.get("calibration"), json.dumps(pred), _now()),
        )
        con.commit()
    finally:
        con.close()


def save_acmg(variant_id: int | None, patient_id: int | None, acmg: dict[str, Any]) -> None:
    con = connect()
    try:
        con.execute(
            """INSERT INTO acmg_interpretations (variant_id, patient_id, classification, criteria_json,
               evidence_summary, rule_engine_version, created_at) VALUES (?,?,?,?,?,?,?)""",
            (variant_id, patient_id, acmg.get("classification"), json.dumps(acmg.get("criteria", [])),
             acmg.get("rule_note") or acmg.get("evidence_summary"),
             acmg.get("framework") or acmg.get("rule_engine_version") or "acmg-v2", _now()),
        )
        con.commit()
    finally:
        con.close()


def save_reconciliation(variant_id: int | None, patient_id: int | None, rec: dict[str, Any]) -> None:
    con = connect()
    try:
        con.execute(
            """INSERT INTO reconciliations (variant_id, patient_id, ml_classification, acmg_classification,
               final_classification, confidence, explanation, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (variant_id, patient_id, rec.get("ml_classification") or rec.get("ml_bucket"),
             rec.get("acmg_classification") or rec.get("final_classification"),
             rec.get("final_classification"), rec.get("confidence"), rec.get("note") or rec.get("explanation"),
             _now()),
        )
        con.commit()
    finally:
        con.close()


def save_therapy(patient_id: int | None, variant_id: int | None, payload: dict[str, Any]) -> None:
    con = connect()
    try:
        con.execute(
            "INSERT INTO therapy_results (patient_id, variant_id, payload_json, created_at) VALUES (?,?,?,?)",
            (patient_id, variant_id, json.dumps(payload), _now()),
        )
        con.commit()
    finally:
        con.close()


def replace_graph(patient_id: int, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> None:
    con = connect()
    try:
        con.execute("DELETE FROM knowledge_graph_relationships WHERE patient_id=?", (patient_id,))
        con.execute("DELETE FROM knowledge_graph_entities WHERE patient_id=?", (patient_id,))
        for n in nodes:
            con.execute(
                """INSERT OR REPLACE INTO knowledge_graph_entities
                   (patient_id, entity_key, entity_type, label, sublabel) VALUES (?,?,?,?,?)""",
                (patient_id, n["id"], n.get("type", "entity"), n.get("label", n["id"]), n.get("sublabel")),
            )
        for e in edges:
            con.execute(
                """INSERT INTO knowledge_graph_relationships (patient_id, source_key, target_key, relation)
                   VALUES (?,?,?,?)""",
                (patient_id, e["source"], e["target"], e.get("relation", "related")),
            )
        con.commit()
    finally:
        con.close()


def get_graph(patient_id: int) -> dict[str, Any]:
    con = connect()
    try:
        nodes = [dict(r) for r in con.execute(
            "SELECT entity_key AS id, entity_type AS type, label, sublabel FROM knowledge_graph_entities WHERE patient_id=?",
            (patient_id,)).fetchall()]
        edges = [dict(r) for r in con.execute(
            "SELECT source_key AS source, target_key AS target, relation FROM knowledge_graph_relationships WHERE patient_id=?",
            (patient_id,)).fetchall()]
        return {"patient_id": patient_id, "nodes": nodes, "edges": edges}
    finally:
        con.close()


def append_provenance(*, patient_id: int | None, event_type: str, function_name: str,
                      payload: dict[str, Any]) -> dict[str, Any]:
    import hashlib
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload_hash = hashlib.sha256(blob.encode()).hexdigest()
    ts = _now()
    con = connect()
    try:
        prev = con.execute(
            "SELECT block_number, block_hash FROM provenance_blocks ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if prev:
            block_number = prev[0] + 1
            previous_hash = prev[1]
        else:
            block_number = 1
            previous_hash = "0" * 64
        block_hash = hashlib.sha256(
            f"{previous_hash}|{payload_hash}|{ts}|{event_type}|{function_name}".encode()
        ).hexdigest()
        cur = con.execute(
            """INSERT INTO provenance_blocks (block_number, previous_hash, payload_hash, block_hash,
               patient_id, event_type, contract_name, function_name, payload_json, timestamp, verification_status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (block_number, previous_hash, payload_hash, block_hash, patient_id, event_type,
             "ClinicalContract", function_name, blob, ts, "recorded"),
        )
        con.commit()
        return dict(con.execute("SELECT * FROM provenance_blocks WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        con.close()


def list_provenance(patient_id: int | None = None) -> list[dict[str, Any]]:
    con = connect()
    try:
        if patient_id is None:
            rows = con.execute("SELECT * FROM provenance_blocks ORDER BY id").fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM provenance_blocks WHERE patient_id=? ORDER BY id", (patient_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def verify_block(block_id: int) -> dict[str, Any]:
    import hashlib
    con = connect()
    try:
        rows = [dict(r) for r in con.execute("SELECT * FROM provenance_blocks ORDER BY id").fetchall()]
        target = next((r for r in rows if r["id"] == block_id), None)
        if not target:
            raise KeyError(block_id)
        checks = []
        prev = "0" * 64
        intact_all = True
        for r in rows:
            expected = hashlib.sha256(
                f"{r['previous_hash']}|{r['payload_hash']}|{r['timestamp']}|{r['event_type']}|{r['function_name']}".encode()
            ).hexdigest()
            intact = r["block_hash"] == expected and r["previous_hash"] == prev
            if not intact:
                intact_all = False
            checks.append({"block_number": r["block_number"], "intact": intact})
            prev = r["block_hash"]
        status = "verified" if intact_all else "tamper_detected"
        con.execute("UPDATE provenance_blocks SET verification_status=? WHERE id=?", (status, block_id))
        con.commit()
        return {
            "verified": intact_all,
            "status": status,
            "tx_id": str(target["id"]),
            "record": target,
            "checks": checks,
            "chain_depth": len(rows),
        }
    finally:
        con.close()


def audit(user_id: int | None, patient_id: int | None, action: str, resource: str,
          resource_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
    con = connect()
    try:
        con.execute(
            """INSERT INTO audit_logs (user_id, patient_id, action, resource, resource_id, timestamp, metadata_json)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, patient_id, action, resource, resource_id, _now(),
             json.dumps(metadata or {})),
        )
        con.commit()
    finally:
        con.close()


def list_audit(patient_id: int) -> list[dict[str, Any]]:
    con = connect()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM audit_logs WHERE patient_id=? ORDER BY id", (patient_id,)
        ).fetchall()]
    finally:
        con.close()


def counts() -> dict[str, int]:
    con = connect()
    try:
        def n(table: str) -> int:
            return int(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        return {
            "users": n("users"),
            "patients": n("patients"),
            "uploads": n("vcf_uploads"),
            "variants": n("variants"),
            "interpretations": n("acmg_interpretations"),
            "provenance_blocks": n("provenance_blocks"),
        }
    finally:
        con.close()


def update_patient(patient_id: int, **fields: Any) -> dict[str, Any]:
    allowed = {
        "age", "sex", "diagnosis", "presenting_complaint", "consent_confirmed",
        "user_id", "email", "full_name", "account_status",
    }
    payload = {k: v for k, v in fields.items() if k in allowed}
    if "consent_confirmed" in payload:
        payload["consent_confirmed"] = 1 if payload["consent_confirmed"] else 0
    payload["updated_at"] = _now()
    sets = ", ".join(f"{k}=?" for k in payload)
    con = connect()
    try:
        con.execute(f"UPDATE patients SET {sets} WHERE id=?", (*payload.values(), patient_id))
        con.commit()
    finally:
        con.close()
    return get_patient(patient_id)


def assign_all_lab_technicians(patient_id: int) -> None:
    con = connect()
    try:
        techs = con.execute("SELECT id FROM users WHERE role='lab_technician'").fetchall()
        for (uid,) in techs:
            con.execute(
                "INSERT OR IGNORE INTO patient_assignments (patient_id, user_id, role) VALUES (?,?,?)",
                (patient_id, uid, "lab_technician"),
            )
        con.commit()
    finally:
        con.close()


def assign_technician_to_existing_patients(user_id: int) -> None:
    con = connect()
    try:
        patients = con.execute("SELECT id FROM patients").fetchall()
        for (pid,) in patients:
            con.execute(
                "INSERT OR IGNORE INTO patient_assignments (patient_id, user_id, role) VALUES (?,?,?)",
                (pid, user_id, "lab_technician"),
            )
        con.commit()
    finally:
        con.close()


def assign_user(patient_id: int, user_id: int, role: str) -> None:
    con = connect()
    try:
        con.execute(
            "INSERT OR IGNORE INTO patient_assignments (patient_id, user_id, role) VALUES (?,?,?)",
            (patient_id, user_id, role),
        )
        if role == "patient":
            con.execute("UPDATE patients SET user_id=? WHERE id=?", (user_id, patient_id))
        con.commit()
    finally:
        con.close()


def find_upload_by_sha(digest: str, uploaded_by: int | None = None) -> dict[str, Any] | None:
    con = connect()
    try:
        if uploaded_by is None:
            return _row(con.execute("SELECT * FROM vcf_uploads WHERE sha256=?", (digest,)).fetchone())
        return _row(con.execute(
            "SELECT * FROM vcf_uploads WHERE sha256=? AND uploaded_by=?",
            (digest, uploaded_by),
        ).fetchone())
    finally:
        con.close()


def list_variants_for(user: dict[str, Any], page: int = 1, page_size: int = 50) -> dict[str, Any]:
    uploads = list_uploads_for(user)
    ids = [u["id"] for u in uploads]
    if not ids:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}
    offset = max(0, (page - 1) * page_size)
    placeholders = ",".join("?" * len(ids))
    con = connect()
    try:
        total = con.execute(
            f"SELECT COUNT(*) FROM variants WHERE vcf_upload_id IN ({placeholders})", ids
        ).fetchone()[0]
        rows = con.execute(
            f"SELECT * FROM variants WHERE vcf_upload_id IN ({placeholders}) ORDER BY id DESC LIMIT ? OFFSET ?",
            (*ids, page_size, offset),
        ).fetchall()
        return {"items": [dict(r) for r in rows], "total": int(total), "page": page, "page_size": page_size}
    finally:
        con.close()


def save_report(patient_id: int | None, variant_id: int | None, payload: dict[str, Any]) -> dict[str, Any]:
    con = connect()
    try:
        cur = con.execute(
            "INSERT INTO reports (patient_id, variant_id, payload_json, created_at) VALUES (?,?,?,?)",
            (patient_id, variant_id, json.dumps(payload, default=str), _now()),
        )
        con.commit()
        return dict(con.execute("SELECT * FROM reports WHERE id=?", (cur.lastrowid,)).fetchone())
    finally:
        con.close()


def latest_report(patient_id: int) -> dict[str, Any] | None:
    con = connect()
    try:
        row = _row(con.execute(
            "SELECT * FROM reports WHERE patient_id=? ORDER BY id DESC LIMIT 1", (patient_id,)
        ).fetchone())
        if not row:
            return None
        row["payload"] = json.loads(row["payload_json"])
        return row
    finally:
        con.close()


def save_workup_snapshot(patient_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    variant = payload.get("variant") or {}
    acmg = payload.get("acmg") or {}
    ml = payload.get("ml") or {}
    recon = payload.get("reconciliation") or {}
    gene = variant.get("gene")
    hgvs = variant.get("hgvs_c")
    label = " ".join(str(x) for x in (gene, hgvs) if x)
    final = recon.get("final_classification") or acmg.get("classification")
    ts = _now()
    con = connect()
    try:
        cur = con.execute(
            """INSERT INTO workup_snapshots
               (patient_id, gene, hgvs_c, variant_label, acmg_classification, ml_top_class,
                final_classification, reconciliation_status, payload_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                patient_id, gene, hgvs, label or None,
                acmg.get("classification"), ml.get("top_class"),
                final, recon.get("status"),
                json.dumps(payload, default=str), ts,
            ),
        )
        con.commit()
        snap_id = cur.lastrowid
    finally:
        con.close()
    save_reconciliation(None, patient_id, {
        "ml_classification": ml.get("top_class"),
        "acmg_classification": acmg.get("classification"),
        "final_classification": final,
        "confidence": recon.get("confidence"),
        "note": recon.get("note") or recon.get("status"),
    })
    save_report(patient_id, None, {"kind": "CLINICAL_WORKUP", "snapshot_id": snap_id, **payload})
    return latest_workup_snapshot(patient_id) or {}


def latest_workup_snapshot(patient_id: int) -> dict[str, Any] | None:
    con = connect()
    try:
        row = _row(con.execute(
            "SELECT * FROM workup_snapshots WHERE patient_id=? ORDER BY id DESC LIMIT 1",
            (patient_id,),
        ).fetchone())
        if not row:
            return None
        row["payload"] = json.loads(row["payload_json"])
        row.pop("payload_json", None)
        return row
    finally:
        con.close()


def patient_for_user(user: dict[str, Any]) -> dict[str, Any] | None:
    rows = list_patients_for(user)
    return rows[0] if rows else None


def insert_observation(
    *,
    patient_id: int,
    variant_id: int,
    source_file_id: int | None,
    observation_date: float | None = None,
    allele_fraction: float | None = None,
    clinical_status: str | None = None,
    source_dataset: str | None = None,
) -> int:
    ts = observation_date if observation_date is not None else _now()
    con = connect()
    try:
        if source_file_id is not None:
            exists = con.execute(
                """SELECT id FROM variant_observations
                   WHERE patient_id=? AND variant_id=? AND source_file_id=?""",
                (patient_id, variant_id, source_file_id),
            ).fetchone()
            if exists:
                return int(exists[0])
        cur = con.execute(
            """INSERT INTO variant_observations
               (patient_id, variant_id, source_file_id, observation_date, allele_fraction,
                clinical_status, source_dataset, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (patient_id, variant_id, source_file_id, ts, allele_fraction,
             clinical_status, source_dataset, _now()),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def record_observations_for_upload(upload_id: int, patient_id: int) -> int:
    """Persist real sample timepoints only. Never invent historical VAF."""
    up = get_upload(upload_id)
    variants = list_variants(upload_id, page=1, page_size=2000)["items"]
    n = 0
    for v in variants:
        insert_observation(
            patient_id=patient_id,
            variant_id=v["id"],
            source_file_id=upload_id,
            observation_date=up.get("uploaded_at"),
            allele_fraction=v.get("allele_fraction"),
            source_dataset="UPLOADED_FILE",
        )
        n += 1
    return n


def longitudinal_for_patient(patient_id: int) -> dict[str, Any]:
    con = connect()
    try:
        rows = [
            dict(r)
            for r in con.execute(
                """SELECT o.*, v.chromosome, v.position, v.reference, v.alternate, v.gene,
                          v.normalized_variant, v.source_type, u.filename
                   FROM variant_observations o
                   JOIN variants v ON v.id=o.variant_id
                   LEFT JOIN vcf_uploads u ON u.id=o.source_file_id
                   WHERE o.patient_id=?
                   ORDER BY o.observation_date ASC, o.id ASC""",
                (patient_id,),
            ).fetchall()
        ]
    finally:
        con.close()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = row.get("normalized_variant") or (
            f"{row.get('chromosome')}:{row.get('position')}:{row.get('reference')}>{row.get('alternate')}"
        )
        grouped.setdefault(key, []).append(row)
    series = []
    for key, points in grouped.items():
        unique_files = {p.get("source_file_id") for p in points if p.get("source_file_id") is not None}
        series.append({
            "variant_key": key,
            "gene": points[0].get("gene"),
            "source_type": points[0].get("source_type"),
            "observation_count": len(points),
            "points": [
                {
                    "observation_date": p["observation_date"],
                    "allele_fraction": p["allele_fraction"],
                    "filename": p.get("filename"),
                    "source_file_id": p.get("source_file_id"),
                    "clinical_status": p.get("clinical_status"),
                }
                for p in points
            ],
            "trajectory_available": len(unique_files) >= 2 or len(points) >= 2,
        })
    multi = any(s["trajectory_available"] for s in series)
    return {
        "patient_id": patient_id,
        "series": series,
        "observation_count": len(rows),
        "trajectory_available": multi,
        "message": (
            None
            if multi
            else (
                "Single observation — longitudinal trajectory unavailable."
                if rows
                else "No variant observations recorded for this patient."
            )
        ),
        "outcome": {
            "supported": False,
            "message": "No validated outcome prediction available.",
            "note": (
                "GenoGuide does not estimate time-to-death from a genomic variant. "
                "Research risk estimation requires a licensed longitudinal outcome dataset "
                "and a held-out evaluated model for that endpoint."
            ),
        },
    }


def append_report_review(
    patient_id: int,
    *,
    reviewed_by: int,
    lab_notes: str | None,
    review_status: str | None,
) -> dict[str, Any]:
    latest = latest_report(patient_id)
    payload = dict(latest.get("payload") or {}) if latest else {}
    payload["lab_review"] = {
        "notes": lab_notes,
        "status": review_status or "REVIEWED",
        "reviewed_by": reviewed_by,
        "reviewed_at": _now(),
    }
    return save_report(patient_id, latest.get("variant_id") if latest else None, payload)


def public_patient(row: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id", "uuid", "identifier", "user_id", "created_by", "email", "full_name",
        "account_status", "age", "sex", "diagnosis", "presenting_complaint",
        "consent_confirmed", "created_at", "updated_at",
    )
    return {k: row.get(k) for k in keys}


def _hash_invite(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_invitation(patient_id: int, created_by: int, ttl_seconds: int = 7 * 86400) -> str:
    raw = secrets.token_urlsafe(32)
    digest = _hash_invite(raw)
    ts = _now()
    con = connect()
    try:
        con.execute(
            "UPDATE patient_invitations SET used_at=? WHERE patient_id=? AND used_at IS NULL",
            (ts, patient_id),
        )
        con.execute(
            """INSERT INTO patient_invitations
               (patient_id, token_hash, created_by, created_at, expires_at)
               VALUES (?,?,?,?,?)""",
            (patient_id, digest, created_by, ts, ts + ttl_seconds),
        )
        con.execute(
            "UPDATE patients SET account_status='invited', updated_at=? WHERE id=? AND user_id IS NULL",
            (ts, patient_id),
        )
        con.commit()
    finally:
        con.close()
    return raw


def peek_invitation(token: str) -> dict[str, Any] | None:
    digest = _hash_invite(token)
    con = connect()
    try:
        row = _row(con.execute(
            """SELECT i.*, p.identifier, p.uuid, p.account_status, p.user_id
               FROM patient_invitations i JOIN patients p ON p.id=i.patient_id
               WHERE i.token_hash=?""",
            (digest,),
        ).fetchone())
        return row
    finally:
        con.close()


def claim_invitation(token: str, user: dict[str, Any]) -> dict[str, Any]:
    if user["role"] != "patient":
        raise PermissionError("only a patient account can claim a patient record")
    row = peek_invitation(token)
    if not row:
        raise KeyError("unknown invitation")
    if row.get("used_at"):
        raise ValueError("invitation already used")
    if float(row["expires_at"]) < _now():
        raise ValueError("invitation expired")
    if row.get("user_id") and int(row["user_id"]) != int(user["id"]):
        raise ValueError("patient record is already linked")
    pid = int(row["patient_id"])
    ts = _now()
    con = connect()
    try:
        con.execute(
            "UPDATE patients SET user_id=?, account_status='active', updated_at=? WHERE id=?",
            (user["id"], ts, pid),
        )
        con.execute(
            "UPDATE patient_invitations SET used_at=?, used_by=? WHERE id=?",
            (ts, user["id"], row["id"]),
        )
        con.execute(
            """INSERT OR IGNORE INTO patient_assignments
               (patient_id, user_id, role, assigned_at, assigned_by, status)
               VALUES (?,?,?,?,?,?)""",
            (pid, user["id"], "patient", ts, user["id"], "active"),
        )
        con.commit()
    finally:
        con.close()
    return get_patient(pid)


def can_access_upload(user: dict[str, Any], upload: dict[str, Any]) -> bool:
    if user["role"] == "lab_technician":
        return True
    if upload.get("uploaded_by") == user["id"]:
        return True
    pid = upload.get("patient_id")
    return bool(pid and can_access_patient(user, int(pid)))


def can_access_variant(user: dict[str, Any], variant: dict[str, Any]) -> bool:
    pid = variant.get("patient_id")
    if pid and can_access_patient(user, int(pid)):
        return True
    try:
        up = get_upload(int(variant["vcf_upload_id"]))
    except (KeyError, TypeError, ValueError):
        return False
    return can_access_upload(user, up)


def get_report(report_id: int) -> dict[str, Any]:
    con = connect()
    try:
        row = _row(con.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone())
        if not row:
            raise KeyError(report_id)
        row["payload"] = json.loads(row["payload_json"])
        return row
    finally:
        con.close()


def can_access_report(user: dict[str, Any], report: dict[str, Any]) -> bool:
    pid = report.get("patient_id")
    if pid is None:
        return user["role"] == "lab_technician"
    return can_access_patient(user, int(pid))


def patient_workspace(patient_id: int) -> dict[str, Any]:
    bundle = patient_bundle(patient_id)
    report = latest_report(patient_id)
    return {
        "linked": True,
        "patient": public_patient(bundle["patient"]),
        "phenotypes": bundle["phenotypes"],
        "family_history": bundle["family_history"],
        "medications": bundle["medications"],
        "uploads": bundle["uploads"],
        "reconciliations": bundle["reconciliations"],
        "workup": bundle.get("workup") or latest_workup_snapshot(patient_id),
        "report": report,
        "graph": get_graph(patient_id),
        "provenance": {
            "blocks": list_provenance(patient_id),
        },
        "audit": list_audit(patient_id),
        "longitudinal": longitudinal_for_patient(patient_id),
    }


def integrity_report() -> dict[str, Any]:
    con = connect()
    try:
        def count(sql: str) -> int:
            return int(con.execute(sql).fetchone()[0])
        return {
            "patients_missing_uuid": count("SELECT COUNT(*) FROM patients WHERE uuid IS NULL OR uuid=''"),
            "uploads_missing_patient": count(
                "SELECT COUNT(*) FROM vcf_uploads WHERE patient_id IS NULL AND file_type!='curated'"
            ),
            "variants_missing_upload": count(
                "SELECT COUNT(*) FROM variants v LEFT JOIN vcf_uploads u ON u.id=v.vcf_upload_id WHERE u.id IS NULL"
            ),
            "reports_missing_patient": count(
                "SELECT COUNT(*) FROM reports WHERE patient_id IS NOT NULL AND patient_id NOT IN (SELECT id FROM patients)"
            ),
            "interpretations_missing_patient": count(
                "SELECT COUNT(*) FROM acmg_interpretations WHERE patient_id IS NOT NULL AND patient_id NOT IN (SELECT id FROM patients)"
            ),
            "provenance_missing_patient": count(
                "SELECT COUNT(*) FROM provenance_blocks WHERE patient_id IS NOT NULL AND patient_id NOT IN (SELECT id FROM patients)"
            ),
        }
    finally:
        con.close()
