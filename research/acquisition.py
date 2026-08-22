"""
Manifest-driven dataset acquisition.

Every download is explicit, checksummed, and receipted: a DATASET_INFO.json
is written next to the data recording source URL, version, license, download
date, size, and SHA-256. `verify` recomputes checksums against receipts.
Nothing here runs implicitly at import or server start.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "research" / "data" / "manifest.yaml"


def load_manifest() -> dict[str, dict[str, Any]]:
    with open(MANIFEST_PATH) as f:
        return yaml.safe_load(f)["datasets"]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while data := f.read(chunk):
            h.update(data)
    return h.hexdigest()


def _receipt_path(dest: Path) -> Path:
    base = dest if dest.is_dir() else dest.parent
    return base / "DATASET_INFO.json"


def dataset_status(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    dest = REPO_ROOT / spec["destination"]
    receipt = _receipt_path(dest)
    present = dest.exists() and (not dest.is_dir() or any(dest.iterdir()))
    info = json.loads(receipt.read_text()) if receipt.exists() else None
    return {
        "name": name,
        "present": present,
        "auto_downloadable": bool(spec.get("auto_downloadable")),
        "license": spec.get("license", ""),
        "receipt": info,
        "destination": str(dest.relative_to(REPO_ROOT)),
    }


def download(name: str, force: bool = False) -> dict[str, Any]:
    manifest = load_manifest()
    if name not in manifest:
        raise KeyError(f"unknown dataset {name!r}; see `data list`")
    spec = manifest[name]
    if not spec.get("auto_downloadable"):
        raise RuntimeError(
            f"{name} is NOT auto-downloadable: {spec.get('notes', 'see manifest for instructions')}"
        )
    dest = REPO_ROOT / spec["destination"]
    urls = [spec["url"]] + list(spec.get("extra_files") or [])

    if dest.is_dir() or spec["destination"].endswith("/"):
        dest.mkdir(parents=True, exist_ok=True)
        targets = [(u, dest / u.rstrip("/").split("/")[-1]) for u in urls]
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        targets = [(urls[0], dest)] + [
            (u, dest.parent / u.rstrip("/").split("/")[-1]) for u in urls[1:]
        ]

    files: list[dict[str, Any]] = []
    for url, target in targets:
        if target.exists() and not force:
            print(f"  exists, skipping: {target.name} (use --force to redownload)")
        else:
            print(f"  downloading {url}")
            _fetch(url, target)
        files.append({
            "file": target.name,
            "url": url,
            "size_bytes": target.stat().st_size,
            "sha256": sha256_file(target),
        })

    receipt = {
        "dataset": name,
        "version": spec.get("version"),
        "source": spec.get("source"),
        "license": spec.get("license"),
        "citation": spec.get("citation"),
        "genome_build": spec.get("genome_build"),
        "download_date": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    rp = _receipt_path(dest)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(receipt, indent=2))
    return receipt


def _fetch(url: str, target: Path) -> None:
    """curl with resume support; falls back to urllib if curl is unavailable."""
    if shutil.which("curl"):
        subprocess.run(
            ["curl", "-L", "--fail", "--retry", "3", "-C", "-", "-o", str(target), url],
            check=True,
        )
    else:  # pragma: no cover
        import urllib.request

        with urllib.request.urlopen(url) as r, open(target, "wb") as f:
            shutil.copyfileobj(r, f)


def register_existing(name: str) -> dict[str, Any] | None:
    """Write a receipt for data that is already on disk (e.g. pre-fetched)."""
    manifest = load_manifest()
    spec = manifest[name]
    dest = REPO_ROOT / spec["destination"]
    if not dest.exists():
        return None
    files = []
    paths = sorted(p for p in dest.iterdir() if p.is_file() and p.name != "DATASET_INFO.json") if dest.is_dir() else [dest]
    for p in paths:
        files.append({"file": p.name, "url": spec.get("url"),
                      "size_bytes": p.stat().st_size, "sha256": sha256_file(p)})
    receipt = {
        "dataset": name,
        "version": spec.get("version"),
        "source": spec.get("source"),
        "license": spec.get("license"),
        "citation": spec.get("citation"),
        "genome_build": spec.get("genome_build"),
        "download_date": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    _receipt_path(dest).write_text(json.dumps(receipt, indent=2))
    return receipt


def verify(name: str | None = None) -> list[dict[str, Any]]:
    manifest = load_manifest()
    names = [name] if name else list(manifest)
    results = []
    for n in names:
        spec = manifest[n]
        dest = REPO_ROOT / spec["destination"]
        receipt_file = _receipt_path(dest)
        if not receipt_file.exists():
            results.append({"dataset": n, "status": "NO_RECEIPT"})
            continue
        receipt = json.loads(receipt_file.read_text())
        ok = True
        for f in receipt.get("files", []):
            p = (dest if dest.is_dir() else dest.parent) / f["file"]
            if not p.exists():
                ok = False
                results.append({"dataset": n, "file": f["file"], "status": "MISSING"})
                continue
            actual = sha256_file(p)
            if actual != f["sha256"]:
                ok = False
                results.append({"dataset": n, "file": f["file"], "status": "CHECKSUM_MISMATCH"})
        if ok:
            results.append({"dataset": n, "status": "VERIFIED", "files": len(receipt.get("files", []))})
    return results
