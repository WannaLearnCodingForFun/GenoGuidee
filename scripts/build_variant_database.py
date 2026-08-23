#!/usr/bin/env python3
"""Rebuild the processed ClinVar training/annotation tables."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    steps = [
        [sys.executable, "-m", "research.preprocessing.build_clinvar_dataset"],
        [sys.executable, "-m", "research.preprocessing.build_training_dataset"],
    ]
    for cmd in steps:
        print("Running:", " ".join(cmd))
        rc = subprocess.call(cmd, cwd=ROOT)
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
