from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def mini_vcf() -> Path:
    return REPO / "tests/data/mini.vcf"
