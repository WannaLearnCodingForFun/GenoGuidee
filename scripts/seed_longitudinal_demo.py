#!/usr/bin/env python3
"""Seed the marked synthetic longitudinal patient into the local clinical DB."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app import clinical_db as DB
from app.services.longitudinal_demo import seed_longitudinal_demo


def main() -> int:
    DB.init()
    con = DB.connect()
    try:
        row = con.execute("SELECT id FROM users WHERE role='doctor' ORDER BY id LIMIT 1").fetchone()
    finally:
        con.close()
    if not row:
        print("Create a doctor account first (signup), then re-run.")
        return 1
    out = seed_longitudinal_demo(int(row[0]))
    print(out["patient"]["identifier"], out["note"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
