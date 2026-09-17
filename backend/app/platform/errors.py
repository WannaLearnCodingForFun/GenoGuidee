"""Structured platform errors. Does not replace FastAPI default `detail` on legacy routes."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi.responses import JSONResponse


def request_id(explicit: Optional[str] = None) -> str:
    return explicit or uuid.uuid4().hex[:16]


def error_body(code: str, message: str, rid: Optional[str] = None, **extra: Any) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message, "request_id": request_id(rid)}
    err.update(extra)
    return {"error": err}


def json_error(status: int, code: str, message: str, rid: Optional[str] = None, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, rid, **extra))


def disabled(flag: str, rid: Optional[str] = None) -> JSONResponse:
    return json_error(503, "FEATURE_DISABLED", f"{flag} is disabled", rid, flag=flag)
