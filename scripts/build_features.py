#!/usr/bin/env python3
"""Feature-build pointer. Production features are defined in research/preprocessing."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    print("Feature schema: clinvar-tabular-v1 (research/preprocessing).")
    print("ClinVar significance is a LABEL, never a feature. Split must be gene-disjoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
