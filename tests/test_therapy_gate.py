"""Phase B5 — pure gate() function, table-driven over its input space."""
from __future__ import annotations

import pytest

from app.services.therapy_gate import gate


@pytest.mark.parametrize(
    "classification,addressable,review_status,expect_allow",
    [
        ("pathogenic", True, "reviewed", True),
        ("likely_pathogenic", True, "signed_off", True),
        ("pathogenic", True, None, False),  # no sign-off
        ("pathogenic", True, "pending", False),  # not reviewed
        ("pathogenic", False, "reviewed", False),  # not therapy_addressable
        ("vus", True, "reviewed", False),  # VUS never allowed
        ("benign", True, "reviewed", False),
        ("likely_benign", True, "reviewed", False),
        (None, True, "reviewed", False),
        ("Pathogenic", True, "Reviewed", True),  # case-insensitive
        ("pathogenic", False, None, False),  # both gates fail
    ],
)
def test_gate_table(classification, addressable, review_status, expect_allow):
    result = gate(classification, addressable, review_status)
    assert result.allow is expect_allow
    if not expect_allow:
        assert result.reason
    else:
        assert result.reason is None


def test_gate_never_allows_unsigned_pathogenic():
    result = gate("pathogenic", True, None)
    assert result.allow is False
    assert "review" in result.reason.lower() or "sign" in result.reason.lower()


def test_gate_never_allows_non_addressable_even_if_pathogenic_and_signed_off():
    result = gate("pathogenic", False, "reviewed")
    assert result.allow is False
