"""
Optional connector to an external somatic oncology drug-ranking engine.

This module is a DOWNSTREAM advisory branch. It never:
    - changes ACMG classification or criterion status
    - enters ML / XGBoost / logreg feature vectors
    - replaces CPIC/PGx (CYP2D6/Tamoxifen) graph edges
    - emits prescriptions ("start this drug")
    - sends patient identifiers off-box
    - blocks interpretation when the remote host is down

Disabled by default. Enable with:

    GENOGUIDE_DRUG_API_ENABLED=true
    GENOGUIDE_DRUG_API_URL=https://example.ngrok-free.dev

Ngrok-free URLs change every session — never hardcode them.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx

REPO = Path(__file__).resolve().parents[3]
_LOCAL_ENGINE = REPO / "Medical_DrugRecommendation"

from ..schemas.therapy import (
    SomaticTherapy,
    TherapyAvailability,
    TherapyRecommendation,
)
from ..schemas.variant import VariantContext

DISCLAIMER = (
    "External oncology ranking from a separate engine (CIViC / DGIdb / ML hybrid). "
    "Not a prescription. Does not alter ACMG/AMP classification. Review applicable "
    "oncology guidelines with a qualified specialist before any treatment decision. "
    "No patient identifiers are sent to the remote service."
)

_AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "TER": "*", "TRM": "*", "STOP": "*",
}

# Compact tokens the remote engine is known to accept.
KNOWN_INDICATIONS = {
    "NSCLC": "NSCLC", "SCLC": "SCLC", "CRC": "CRC", "GIST": "GIST",
    "CML": "CML", "AML": "AML", "ALL": "ALL", "CLL": "CLL",
    "MELANOMA": "Melanoma", "GBM": "GBM",
}

# Conservative aliases only — never map HBOC / Li-Fraumeni / CF to NSCLC.
_DISEASE_ALIASES = {
    "nsclc": "NSCLC",
    "nonsmall cell lung cancer": "NSCLC",
    "non-small cell lung cancer": "NSCLC",
    "non-small-cell lung cancer": "NSCLC",
    "non small cell lung cancer": "NSCLC",
    "lung adenocarcinoma": "NSCLC",
    "lung adeno": "NSCLC",
    "luad": "NSCLC",
    "sclc": "SCLC",
    "small cell lung cancer": "SCLC",
    "melanoma": "Melanoma",
    "cutaneous melanoma": "Melanoma",
    "crc": "CRC",
    "colorectal cancer": "CRC",
    "colorectal adenocarcinoma": "CRC",
    "colon cancer": "CRC",
    "gist": "GIST",
    "gastrointestinal stromal tumor": "GIST",
    "gastrointestinal stromal tumour": "GIST",
    "cml": "CML",
    "chronic myeloid leukemia": "CML",
    "chronic myeloid leukaemia": "CML",
    "aml": "AML",
    "acute myeloid leukemia": "AML",
    "breast cancer": "Breast Cancer",
    "metastatic breast cancer": "Breast Cancer",
}

_HGVS3 = re.compile(
    r"p\.([A-Za-z]{3})(\d+)([A-Za-z]{3}|\*|Ter|X)\b",
    re.I,
)
_BARE = re.compile(r"^([A-Z*])(\d+)([A-Z*])$")
_UNMAPPABLE = re.compile(r"(fs|del|ins|dup|delins|>)", re.I)

_lock = threading.Lock()
_cache: dict[tuple[str, str, str], tuple[float, SomaticTherapy]] = {}
_fail_count = 0
_circuit_open_until = 0.0

CACHE_TTL_S = 300.0
CIRCUIT_FAILS = 3
CIRCUIT_OPEN_S = 60.0
PATHS = ("/drug-recommendation", "/api/drug-recommendation")
# Docs-only hosts (RFC 2606 .example). Never attempt DNS on these.
_PLACEHOLDER_TLDS = (".example",)


def reset_runtime_state() -> None:
    """Test hook — clear cache and circuit breaker."""
    global _fail_count, _circuit_open_until
    with _lock:
        _cache.clear()
        _fail_count = 0
        _circuit_open_until = 0.0


def validate_base_url(url: str) -> tuple[str, Optional[str]]:
    """Return (cleaned_url, error). error is set for empty / invalid / placeholder hosts."""
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return "", None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        return raw, (
            f"invalid therapy URL {raw!r} — expected https://<live-host> "
            "(not a documentation placeholder)"
        )
    if any(host == tld[1:] or host.endswith(tld) for tld in _PLACEHOLDER_TLDS):
        return raw, (
            f"{host!r} is a documentation placeholder, not a running engine. "
            "Pass the live ngrok/https base URL via --url or GENOGUIDE_DRUG_API_URL."
        )
    return raw, None


def settings(*, base_url: Optional[str] = None) -> dict[str, Any]:
    """Read env at call time so tests can monkeypatch without reimport."""
    url = (base_url if base_url is not None else os.environ.get("GENOGUIDE_DRUG_API_URL", ""))
    url, url_error = validate_base_url(url)
    flag = os.environ.get("GENOGUIDE_DRUG_API_ENABLED", "false").lower()
    flag_on = flag in ("1", "true", "yes", "on") or bool(base_url)
    timeout = float(os.environ.get("GENOGUIDE_DRUG_API_TIMEOUT", "4"))
    local_flag = os.environ.get("GENOGUIDE_DRUG_LOCAL", "true").lower() not in (
        "0", "false", "off", "no",
    )
    return {
        "url": url,
        "url_error": url_error,
        "enabled": flag_on and bool(url) and url_error is None,
        "url_configured": bool(url) and url_error is None,
        "flag_on": flag_on,
        "timeout": max(0.5, min(timeout, 15.0)),
        "host": (urlsplit(url).hostname if url else None),
        "local_engine": local_flag and (_LOCAL_ENGINE / "recommendation" / "recommender.py").exists(),
    }


def connector_status(*, base_url: Optional[str] = None) -> dict[str, Any]:
    s = settings(base_url=base_url)
    return {
        "enabled": s["enabled"] or s.get("local_engine", False),
        "url_configured": s["url_configured"],
        "host": s["host"],
        "url_error": s["url_error"],
        "default": "offline — set GENOGUIDE_DRUG_API_ENABLED=true and GENOGUIDE_DRUG_API_URL, or pass --url",
        "note": "somatic oncology ranking; never overrides ACMG; not CPIC/PGx",
        "circuit_open": time.monotonic() < _circuit_open_until,
        "local_engine": s.get("local_engine", False),
    }


def _describe_remote_error(exc: BaseException, url: str) -> str:
    host = urlsplit(url).hostname or url
    name = type(exc).__name__
    text = str(exc)
    dns = (
        "nodename nor servname" in text
        or "Name or service not known" in text
        or "getaddrinfo failed" in text.lower()
        or "Failed to resolve" in text
    )
    if dns or (isinstance(exc, httpx.ConnectError) and "errno 8" in text.lower()):
        return (
            f"DNS failed for {host!r} ({name}). "
            "GENOGUIDE_DRUG_API_URL must be a live host, not a docs placeholder. "
            f"Tried: {url}"
        )
    if isinstance(exc, (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
        return f"timeout talking to {host!r} ({name}). Tried: {url}"
    return f"remote therapy engine unavailable ({name}: {exc}). Tried: {url}"


def protein_shorthand(value: Optional[str]) -> Optional[str]:
    """Map HGVS.p / one-letter protein change → remote `variant` token (L858R).

    Returns None when the value is genomic, coding HGVS, a frameshift/indel,
    or otherwise unmappable. Callers MUST skip the remote call rather than guess.
    """
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.upper().startswith("GRCH") or re.match(r"^c\.", raw, re.I):
        return None
    if re.search(r":\d+:", raw):  # canonical variant_id
        return None
    s = raw
    if ":p." in s:
        s = "p." + s.split(":p.", 1)[1]
    elif s.startswith("p.") is False and "." in s and "p." not in s.lower():
        return None
    if _UNMAPPABLE.search(s.replace("p.", "")):
        return None
    if s.endswith("=") or s.endswith("p.="):
        return None

    m = _HGVS3.search(s)
    if m:
        ref3, pos, alt3 = m.group(1), m.group(2), m.group(3)
        ref = _AA3.get(ref3.upper())
        alt = "*" if alt3 in ("*", "X", "Ter", "ter", "TER") else _AA3.get(alt3.upper())
        if ref and alt:
            return f"{ref}{pos}{alt}"
        return None

    compact = s[2:] if s.lower().startswith("p.") else s
    m = _BARE.match(compact.upper())
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return None


def normalize_indication(text: Optional[str], *, passthrough: bool = False) -> Optional[str]:
    """Map free-text diagnosis → remote disease token.

    Conservative: hereditary-cancer / CF / cardiomyopathy strings do NOT become NSCLC.
    `passthrough=True` (explicit proxy) sends the trimmed user string if no alias hits.
    """
    if not text:
        return None
    original = str(text).strip()
    if not original:
        return None
    key = re.sub(r"[^a-z0-9+ -]", "", original.lower())
    key = re.sub(r"\s+", " ", key).strip()
    if key in _DISEASE_ALIASES:
        return _DISEASE_ALIASES[key]
    token = original.strip()
    if token.upper() in KNOWN_INDICATIONS:
        return KNOWN_INDICATIONS[token.upper()]
    if passthrough:
        return original
    return None


def _sha(obj: Any) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _empty(availability: TherapyAvailability, reason: str, **extra: Any) -> SomaticTherapy:
    return SomaticTherapy(
        availability=availability, reason=reason, disclaimer=DISCLAIMER, **extra,
    )


def _post_json(url: str, payload: dict[str, str], timeout: float) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "GenoGuide-ResearchEngine/1.0",
        "ngrok-skip-browser-warning": "true",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise ValueError("remote response is not a JSON object")
        return data


def _get_json(url: str, timeout: float) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "GenoGuide-ResearchEngine/1.0",
        "ngrok-skip-browser-warning": "true",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, dict) else {"raw": data}


def probe_health(*, base_url: Optional[str] = None) -> dict[str, Any]:
    s = settings(base_url=base_url)
    if s["url_error"]:
        return {"ok": False, "reason": s["url_error"], "host": s["host"]}
    if not s["url_configured"]:
        return {"ok": False, "reason": "GENOGUIDE_DRUG_API_URL not set"}
    try:
        body = _get_json(f"{s['url']}/health", min(s["timeout"], 3.0))
        return {"ok": True, "health": body, "host": s["host"]}
    except Exception as exc:  # noqa: BLE001 — status probe must never crash
        return {"ok": False, "reason": _describe_remote_error(exc, f"{s['url']}/health"),
                "host": s["host"]}


def _record_failure() -> None:
    global _fail_count, _circuit_open_until
    with _lock:
        _fail_count += 1
        if _fail_count >= CIRCUIT_FAILS:
            _circuit_open_until = time.monotonic() + CIRCUIT_OPEN_S


def _sklearn_pickle_compat() -> None:
    """sklearn 1.7 pickles import top-level `_loss`; 1.8+ moved it under sklearn._loss."""
    if "_loss" in sys.modules:
        return
    try:
        import sklearn._loss._loss as _loss_mod  # type: ignore
        sys.modules["_loss"] = _loss_mod
    except Exception:  # noqa: BLE001 — optional compat for the in-repo pickle
        return


def _inprocess_recommend(payload: dict[str, str]) -> Optional[dict[str, Any]]:
    """Call the in-repo Medical_DrugRecommendation pipeline (unchanged)."""
    if not (_LOCAL_ENGINE / "recommendation" / "recommender.py").exists():
        return None
    if os.environ.get("GENOGUIDE_DRUG_LOCAL", "true").lower() in ("0", "false", "off", "no"):
        return None
    root = str(_LOCAL_ENGINE)
    if root not in sys.path:
        sys.path.insert(0, root)
    _sklearn_pickle_compat()
    try:
        from recommendation.recommender import recommend_drugs  # type: ignore
        raw = recommend_drugs(payload)
        return raw if isinstance(raw, dict) else None
    except Exception:  # noqa: BLE001 — local engine failure falls through to HTTP / empty
        return None


def _somatic_from_raw(raw: dict[str, Any], payload: dict[str, str],
                      endpoint: str, latency_ms: float) -> SomaticTherapy:
    recs = []
    for item in raw.get("recommendations") or []:
        recs.append(TherapyRecommendation(
            drug=str(item.get("drug", "")),
            rank=int(item.get("rank", 0)),
            score=float(item.get("score", 0.0)),
            response=str(item.get("response", "")),
            evidence_level=str(item.get("evidence_level", "")),
            evidence_count=int(item.get("evidence_count", 0)),
        ))
    recs.sort(key=lambda r: r.rank)
    return SomaticTherapy(
        availability=TherapyAvailability.AVAILABLE,
        reason="ranking attached; human review required",
        endpoint=endpoint,
        request=payload,
        request_hash=_sha(payload),
        response_hash=_sha({"recommendations": [r.model_dump() for r in recs]}),
        recommendations=recs,
        human_review_status="required",
        disclaimer=DISCLAIMER,
        cached=False,
        latency_ms=round(latency_ms, 1),
        engine={"gene": raw.get("gene"), "variant": raw.get("variant"),
                "disease": raw.get("disease")},
    )


def _record_success() -> None:
    global _fail_count, _circuit_open_until
    with _lock:
        _fail_count = 0
        _circuit_open_until = 0.0


def recommend(gene: str, variant: str, disease: str,
              *, base_url: Optional[str] = None) -> SomaticTherapy:
    """Call the local in-repo ranker or the remote host. Never raises."""
    s = settings(base_url=base_url)
    if s["url_error"] and (s["flag_on"] or base_url):
        return _empty(TherapyAvailability.SOURCE_NOT_CONFIGURED, s["url_error"])

    gene_s = (gene or "").strip().upper()
    var_s = protein_shorthand(variant) or (variant.strip() if _BARE.match(variant.strip().upper()) else None)
    dis_s = normalize_indication(disease, passthrough=True)
    if not gene_s or not var_s or not dis_s:
        return _empty(TherapyAvailability.SKIPPED,
                      "gene, protein-change variant, and disease are required "
                      "(genomic/c. HGVS is not guessed)")

    payload = {"gene": gene_s, "variant": var_s, "disease": dis_s}
    key = (gene_s, var_s, dis_s)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_S:
            cached = hit[1].model_copy(update={"cached": True})
            return cached

    t0 = time.perf_counter()
    if not base_url:
        raw_local = _inprocess_recommend(payload)
        if raw_local is not None:
            result = _somatic_from_raw(
                raw_local, payload,
                "in-process:Medical_DrugRecommendation",
                (time.perf_counter() - t0) * 1000)
            with _lock:
                _cache[key] = (time.monotonic(), result)
            return result

    if not s["enabled"]:
        reason = ("GENOGUIDE_DRUG_API_ENABLED is false"
                  if not s["flag_on"] else "GENOGUIDE_DRUG_API_URL is empty")
        return _empty(TherapyAvailability.SOURCE_NOT_CONFIGURED, reason)

    with _lock:
        if time.monotonic() < _circuit_open_until:
            return _empty(TherapyAvailability.SOURCE_UNAVAILABLE,
                          "circuit open after repeated remote failures; interpretation continues")

    last_err = "no endpoint succeeded"
    t0 = time.perf_counter()
    for path in PATHS:
        url = f"{s['url']}{path}"
        try:
            raw = _post_json(url, payload, s["timeout"])
            recs = []
            for item in raw.get("recommendations") or []:
                recs.append(TherapyRecommendation(
                    drug=str(item.get("drug", "")),
                    rank=int(item.get("rank", 0)),
                    score=float(item.get("score", 0.0)),
                    response=str(item.get("response", "")),
                    evidence_level=str(item.get("evidence_level", "")),
                    evidence_count=int(item.get("evidence_count", 0)),
                ))
            recs.sort(key=lambda r: r.rank)
            result = SomaticTherapy(
                availability=TherapyAvailability.AVAILABLE,
                reason="remote ranking attached; human review required",
                endpoint=url,
                request=payload,
                request_hash=_sha(payload),
                response_hash=_sha({"recommendations": [r.model_dump() for r in recs]}),
                recommendations=recs,
                human_review_status="required",
                disclaimer=DISCLAIMER,
                cached=False,
                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                engine={"gene": raw.get("gene"), "variant": raw.get("variant"),
                        "disease": raw.get("disease")},
            )
            _record_success()
            with _lock:
                _cache[key] = (time.monotonic(), result)
            return result
        except Exception as exc:  # noqa: BLE001 — remote failure must not raise
            last_err = _describe_remote_error(exc, url)
            continue
    _record_failure()
    return _empty(TherapyAvailability.SOURCE_UNAVAILABLE, last_err,
                  request=payload, request_hash=_sha(payload),
                  latency_ms=round((time.perf_counter() - t0) * 1000, 1))


def resolve_somatic_therapy(
    *,
    gene: Optional[str],
    hgvs_p: Optional[str],
    variant_context: VariantContext,
    include: bool,
    oncology_indication: Optional[str],
    human_review_required: bool,
) -> SomaticTherapy:
    """Decide whether to call the remote engine for an interpretation.

    Germline interpretations skip the call (NOT_APPLICABLE) unless the caller
    explicitly sets include=True. Protein change is mapped from hgvs_p only —
    genomic coordinates are never guessed.
    """
    somatic = variant_context == VariantContext.SOMATIC
    if not include and not somatic:
        return _empty(
            TherapyAvailability.NOT_APPLICABLE,
            "germline interpretation — somatic oncology ranking is opt-in "
            "(set variant_context=SOMATIC or include_somatic_therapy)",
        )

    s = settings()
    if not s["enabled"]:
        return _empty(
            TherapyAvailability.SOURCE_NOT_CONFIGURED,
            "therapy connector disabled (offline default); "
            "set GENOGUIDE_DRUG_API_ENABLED=true to attach rankings",
        )

    protein = protein_shorthand(hgvs_p)
    if not protein:
        return _empty(
            TherapyAvailability.SKIPPED,
            "unmappable protein change — will not guess L858R-style tokens "
            "from genomic or c. HGVS coordinates",
        )
    if not gene:
        return _empty(TherapyAvailability.SKIPPED, "gene symbol required for therapy ranking")

    disease = normalize_indication(oncology_indication, passthrough=False)
    if not disease:
        return _empty(
            TherapyAvailability.SKIPPED,
            "no oncology indication mapped (pass patient.oncology_indication "
            "such as NSCLC; germline disease names are not forwarded)",
        )

    result = recommend(gene, protein, disease)
    note = result.reason or ""
    if human_review_required:
        extra = "ACMG/reconciliation already requires human review — rankings are advisory only."
        note = f"{note}; {extra}" if note else extra
    return result.model_copy(update={
        "reason": note,
        "human_review_status": "required",
        "disclaimer": DISCLAIMER,
    })
