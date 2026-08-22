"""Central configuration for the GenoGuide backend."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "model_store"
DB_PATH = BASE_DIR / "genoguide.db"

DATA_DIR.mkdir(exist_ok=True)
MODEL_DIR.mkdir(exist_ok=True)

# DEMO_MODE (default): precomputed deterministic ESM-2 embeddings + curated
# probabilities for showcase variants. Guarantees a fully offline, reproducible demo.
# LIVE_MODE: real ESM-2 (esm2_t6_8M_UR50D) inference if torch + fair-esm are installed.
DEMO_MODE = os.environ.get("GENOGUIDE_MODE", "demo").lower() != "live"

MODEL_VERSION = "genoguide-xgb-1.3.0"
ESM_MODEL_NAME = "esm2_t6_8M_UR50D"
ESM_EMBED_DIM = 320
EVIDENCE_VERSION = "acmg-amp-2015.r4 / demo-evidence-2026.08"
CONTRACT_INTERPRETATION = "InterpretationContract"
CONTRACT_CONSENT = "ConsentContract"
LEDGER_CHANNEL = "genoguide-provenance-local"

RANDOM_SEED = 42

# Optional somatic oncology ranking engine (disabled so offline demo/pytest
# never depend on an external host). Ngrok URLs change — set via env, never
# hardcode. Drug scores MUST NOT enter ACMG or ML features.
#   GENOGUIDE_DRUG_API_URL=https://host.example
#   GENOGUIDE_DRUG_API_ENABLED=true
#   GENOGUIDE_DRUG_API_TIMEOUT=4
DRUG_API_URL = os.environ.get("GENOGUIDE_DRUG_API_URL", "").rstrip("/")
DRUG_API_ENABLED = os.environ.get("GENOGUIDE_DRUG_API_ENABLED", "false").lower() in (
    "1", "true", "yes", "on",
)
