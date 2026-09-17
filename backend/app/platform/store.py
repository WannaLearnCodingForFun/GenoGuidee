"""Thin clinical.db helpers for the platform layer."""
from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..clinical_db import connect


def now() -> float:
    return time.time()


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def loads(raw: Optional[str], default: Any = None) -> Any:
    if not raw:
        return default
    return json.loads(raw)


def execute(sql: str, params: tuple = (), fetch: str = "none") -> Any:
    con = connect()
    try:
        cur = con.execute(sql, params)
        if fetch == "one":
            row = cur.fetchone()
            con.commit()
            return row
        if fetch == "all":
            rows = cur.fetchall()
            con.commit()
            return rows
        con.commit()
        return cur.lastrowid
    finally:
        con.close()


def audit(*, who: Optional[str], what: str, case_id: Optional[str] = None,
          object: Optional[str] = None, before: Any = None, after: Any = None,
          reason: Optional[str] = None, request_id: Optional[str] = None) -> None:
    execute(
        """INSERT INTO platform_audit
           (who, what, when_ts, case_id, object, before_json, after_json, reason, request_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (who, what, now(), case_id, object,
         dumps(before) if before is not None else None,
         dumps(after) if after is not None else None,
         reason, request_id),
    )
