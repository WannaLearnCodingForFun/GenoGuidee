"""Additive SQLite migrations. Never DROP TABLE."""
from __future__ import annotations

import sqlite3

PLATFORM_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_platform_roles (
  user_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  granted_at REAL NOT NULL,
  PRIMARY KEY (user_id, role)
);
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL UNIQUE,
  patient_id INTEGER,
  created_by INTEGER,
  created_at REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'open'
);
CREATE TABLE IF NOT EXISTS evidence_graph_nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_key TEXT NOT NULL UNIQUE,
  node_type TEXT NOT NULL,
  label TEXT NOT NULL,
  properties_json TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence_graph_edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_key TEXT NOT NULL,
  target_key TEXT NOT NULL,
  edge_type TEXT NOT NULL,
  source TEXT NOT NULL,
  source_id TEXT,
  source_version TEXT,
  retrieved_at TEXT NOT NULL,
  evidence_strength TEXT,
  direction TEXT,
  properties_json TEXT,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_egraph_src ON evidence_graph_edges(source_key);
CREATE INDEX IF NOT EXISTS idx_egraph_tgt ON evidence_graph_edges(target_key);
CREATE TABLE IF NOT EXISTS interpretation_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interpretation_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  variant_id TEXT,
  case_id TEXT,
  patient_id INTEGER,
  classification TEXT NOT NULL,
  acmg_criteria_json TEXT,
  ml_prediction_json TEXT,
  model_version TEXT,
  phenotype_score REAL,
  evidence_ids_json TEXT,
  kg_version TEXT,
  guideline_version TEXT,
  reviewer TEXT,
  curation_state TEXT NOT NULL DEFAULT 'AI_DRAFT',
  payload_json TEXT NOT NULL,
  provenance_json TEXT,
  created_at REAL NOT NULL,
  UNIQUE(interpretation_id, version)
);
CREATE INDEX IF NOT EXISTS idx_interp_ver ON interpretation_versions(interpretation_id);
CREATE TABLE IF NOT EXISTS evidence_source_versions (
  source TEXT PRIMARY KEY,
  version TEXT,
  fingerprint TEXT,
  metadata_json TEXT,
  checked_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reanalysis_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  created_at REAL NOT NULL,
  finished_at REAL,
  payload_json TEXT
);
CREATE TABLE IF NOT EXISTS reanalysis_changes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT,
  variant_id TEXT,
  interpretation_id TEXT,
  change_type TEXT NOT NULL,
  payload_json TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS watchlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  patient_id INTEGER,
  case_id TEXT,
  variant_id TEXT,
  created_by INTEGER,
  created_at REAL NOT NULL,
  last_checked REAL,
  last_evidence_version TEXT,
  status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS watchlist_triggers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  watchlist_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  evidence_change TEXT,
  classification_before TEXT,
  classification_after TEXT,
  review_required INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS curation_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interpretation_id TEXT NOT NULL,
  actor TEXT,
  role TEXT,
  action TEXT NOT NULL,
  object TEXT,
  before_json TEXT,
  after_json TEXT,
  reason TEXT,
  request_id TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS acmg_simulations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  interpretation_id TEXT,
  official_classification TEXT,
  simulated_classification TEXT,
  modifications_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at REAL NOT NULL,
  official INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS phenopacket_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT,
  patient_id INTEGER,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cohorts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cohort_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_by INTEGER,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS cohort_cases (
  cohort_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  patient_id INTEGER,
  PRIMARY KEY (cohort_id, case_id)
);
CREATE TABLE IF NOT EXISTS model_monitor_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  drift_level TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS platform_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  who TEXT,
  what TEXT NOT NULL,
  when_ts REAL NOT NULL,
  case_id TEXT,
  object TEXT,
  before_json TEXT,
  after_json TEXT,
  reason TEXT,
  request_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_plat_audit_when ON platform_audit(when_ts);
"""


def _add_col(con: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    if not cols:
        return
    if name not in cols:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def apply_platform_schema(con: sqlite3.Connection) -> None:
    con.executescript(PLATFORM_SCHEMA)
    _add_col(con, "patient_phenotypes", "status", "TEXT DEFAULT 'observed'")
    _add_col(con, "patient_phenotypes", "onset", "TEXT")
    _add_col(con, "patient_phenotypes", "observed_at", "REAL")
    _add_col(con, "patient_phenotypes", "confidence", "TEXT")
    _add_col(con, "patient_phenotypes", "negated", "INTEGER DEFAULT 0")
    _add_col(con, "patient_phenotypes", "temporality", "TEXT")
    _add_col(con, "patient_phenotypes", "severity", "TEXT")
    _add_col(con, "ml_predictions", "entropy", "REAL")
    _add_col(con, "ml_predictions", "ood_score", "REAL")
    _add_col(con, "ml_predictions", "ood_state", "TEXT")
