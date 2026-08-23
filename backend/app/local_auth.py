"""Local password auth used when Supabase is not configured."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Optional

from fastapi import Depends, Header, HTTPException

from . import clinical_db as DB

ITER = 210_000
SECRET = os.environ.get("GENOGUIDE_SECRET_KEY", "genoguide-local-dev-only")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITER)
    return f"pbkdf2${ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt_hex, dk_hex = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def issue_token(user: dict[str, Any]) -> str:
    payload = {"uid": user["id"], "role": user["role"], "exp": int(time.time()) + 86400 * 7}
    body = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body.encode().hex()}.{sig}"


def parse_token(token: str) -> dict[str, Any]:
    try:
        body_hex, sig = token.split(".", 1)
        body = bytes.fromhex(body_hex)
        expect = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            raise ValueError("bad signature")
        payload = json.loads(body.decode())
        if int(payload["exp"]) < time.time():
            raise ValueError("expired")
        return payload
    except Exception as exc:
        raise HTTPException(401, "invalid or expired session") from exc


def require_user(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    payload = parse_token(authorization.split(" ", 1)[1].strip())
    try:
        user = DB.get_user(int(payload["uid"]))
    except KeyError as exc:
        raise HTTPException(401, "unknown user") from exc
    return user


def require_roles(*roles: str):
    def checker(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
        if user["role"] not in roles:
            raise HTTPException(403, f"This action is limited to: {', '.join(roles)}.")
        return user
    return checker


def require_patient_access(patient_id: int, user: dict[str, Any]) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        raise HTTPException(403, "You do not have access to this patient.")
    return DB.get_patient(patient_id)
