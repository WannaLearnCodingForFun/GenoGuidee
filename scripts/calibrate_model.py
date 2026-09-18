#!/usr/bin/env python3
"""Calibration pointer. HQ binary uses isotonic on the validation split (threshold 0.175)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def main() -> int:
    print("See research/training/calibration.py and docs/model_evaluation.md.")
    print("Do not invent displayed probabilities. finalize_prediction renormalizes to sum=1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
