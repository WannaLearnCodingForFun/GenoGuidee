#!/usr/bin/env python3
"""Download legitimate public genomic datasets via the existing CLI."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cmd = [sys.executable, "-m", "cli.genoguide", "data", "download", "clinvar_variant_summary"]
    print("Running:", " ".join(cmd))
    print("Other sources: python -m cli.genoguide data list")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
