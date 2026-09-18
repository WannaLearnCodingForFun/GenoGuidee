#!/usr/bin/env python3
"""Thin entry to the existing research preprocessing pipeline. Does not download huge files by default."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    print("Use research/preprocessing and scripts/download_datasets.py --help.")
    print("Production training dataset: research/data/processed/training_dataset.parquet")
    print("A small fixture lives under tests/data/. Do not silently fetch ClinVar in this script.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
