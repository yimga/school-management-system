"""Tenant-export integrity hash helpers.

12-pillar audit P7 follow-up. Exports from `apps/reports/compliance_exports.py`
ship to operators / regulators (WAEC, Ofsted, Ministry) as CSVs.
Without a tamper-evidence hash the operator can't prove the file
they handed over is the same one the platform generated.

This module provides:

* :func:`compute_export_hash(payload_bytes)` — SHA-256 in hex.
* :func:`build_manifest(school, export_key, payload, generated_at)` —
  build a JSON manifest with the hash + tenant identity + a generation
  timestamp + the export key.
* :func:`verify_manifest(manifest, payload)` — verify a returned
  manifest matches the bytes (constant-time compare).

Operators include the manifest alongside the CSV when handing the
file off. Auditors later run :func:`verify_manifest` to confirm
nothing was edited after generation.

No new model is introduced — the manifest is JSON output, consumed
by the existing :func:`generate_regional_compliance_export` (SOT
batch 1108) at the boundary where the CSV is materialised.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any


_HASH_ALGO = "sha256"


def compute_export_hash(payload: bytes) -> str:
    """SHA-256 hex digest over the raw CSV bytes.

    Use the bytes that will actually be persisted / transmitted —
    NOT a Python string that might re-encode under a different
    locale on the auditor's side.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("compute_export_hash expects bytes")
    return hashlib.new(_HASH_ALGO, payload).hexdigest()


def build_manifest(
    *,
    school,
    export_key: str,
    payload: bytes,
    generated_at: datetime | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-serializable manifest dict.

    ``school`` may be the live model instance or a ``SimpleNamespace``
    shaped object (for tests). Required attributes: ``id``,
    ``slug``, optionally ``name``.
    """
    school_id = getattr(school, "id", None)
    if school_id is None:
        raise ValueError("school must have .id")
    slug = getattr(school, "slug", "") or ""
    name = getattr(school, "name", "") or ""
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "school_id": int(school_id),
        "school_slug": str(slug),
        "school_name": str(name),
        "export_key": str(export_key),
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "byte_count": len(payload),
        "hash_algorithm": _HASH_ALGO,
        "hash_hex": compute_export_hash(payload),
    }
    if extra:
        manifest["extra"] = dict(extra)
    return manifest


def manifest_to_json(manifest: dict[str, Any]) -> str:
    """Stable JSON serialization (sorted keys + LF endings).

    Sorted keys + a single newline make the manifest itself easy to
    hash + diff in downstream tools.
    """
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def verify_manifest(manifest: dict[str, Any], payload: bytes) -> bool:
    """Constant-time check that ``payload`` matches the recorded hash."""
    if not isinstance(manifest, dict):
        return False
    expected = manifest.get("hash_hex")
    if not isinstance(expected, str):
        return False
    actual = compute_export_hash(payload)
    return hmac.compare_digest(expected, actual)


__all__ = [
    "compute_export_hash",
    "build_manifest",
    "manifest_to_json",
    "verify_manifest",
]
