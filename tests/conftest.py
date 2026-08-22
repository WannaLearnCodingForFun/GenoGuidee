from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def mini_vcf() -> Path:
    return REPO / "tests/data/mini.vcf"


@pytest.fixture(autouse=True)
def _therapy_connector_offline_by_default(monkeypatch):
    """Pytest must not inherit a live/placeholder URL from the developer shell."""
    monkeypatch.delenv("GENOGUIDE_DRUG_API_ENABLED", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_URL", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_TIMEOUT", raising=False)
    monkeypatch.setenv("GENOGUIDE_DRUG_LOCAL", "false")
