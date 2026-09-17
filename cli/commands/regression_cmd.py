"""Run the full pytest regression suite (legacy + platform)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run() -> int:
    cmd = [sys.executable, "-m", "pytest", "-q"]
    return subprocess.call(cmd, cwd=REPO)
