"""Client-side offline proof status, resolved from recorded harness evidence.

Background
----------
Every blueprint's local-first manifest used to report a hardcoded
``browser_proof_status="PARTIAL_CLIENT_HARNESS_REQUIRED"``. That literal was
written when no browser harness existed — but it stayed after
``scripts/verify_client_offline_endurance.py`` (a real Chrome/selenium harness
proving restart persistence + storage pressure) landed. A hardcoded proof
status is the same defect class as the hardcoded "72" readiness meter: it
measures nothing, it can never move, and it caps blueprint readiness at 80
forever no matter what the platform actually proves.

This module replaces the literal with a resolution over *recorded evidence*:
the harness writes a JSON artifact when (and only when) every leg passes, and
this resolver reports ``BROWSER_PROOF_VERIFIED`` only when that artifact is
present, complete, and still describes the code that is on disk right now.

Self-invalidating by design
---------------------------
The artifact records a SHA-256 of each client source it proves. If
``rmc-offline-auth-vault.js`` changes after the proof was recorded, the hashes
no longer match and the status falls back to pending — an old proof can never
vouch for new code. That is a *must-fire* property: it is exercised by a test
that mutates the source and asserts the status drops.

Nothing here fabricates a pass. Missing, unreadable, failed, incomplete, or
stale evidence all resolve to the pending status with a machine-readable
``reason``, which the tenant UI surfaces verbatim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from django.conf import settings as dj_settings


#: Emitted when recorded evidence proves the client legs against current code.
BROWSER_PROOF_VERIFIED = "BROWSER_PROOF_VERIFIED"
#: Emitted in every other case. Kept byte-identical to the historical literal so
#: stored manifests, dashboards, and audits written before this module read the
#: same value for the same meaning.
BROWSER_PROOF_PENDING = "PARTIAL_CLIENT_HARNESS_REQUIRED"

#: Server-side seven-day rails are proven by a Django test that runs in the
#: normal suite, so this one is genuinely static — it is not a placeholder.
SERVER_PROOF_PRESENT = "SERVER_SEVEN_DAY_RAILS_PRESENT"

_ROOT = Path(__file__).resolve().parents[2]

#: Client sources the harness actually exercises. A change to any of them
#: invalidates a recorded proof.
PROVEN_SOURCES: tuple[str, ...] = ("static/js/rmc-offline-auth-vault.js",)

#: Legs the harness must report as passing for the proof to count.
REQUIRED_LEGS: tuple[str, ...] = ("restart_persistence", "storage_pressure")

_DEFAULT_EVIDENCE_PATH = _ROOT / "var" / "offline-client-endurance-proof.json"

_cache: tuple[Any, dict[str, Any]] | None = None


def evidence_path() -> Path:
    """Where the harness writes, and this resolver reads, the proof artifact."""
    override = getattr(dj_settings, "RMC_OFFLINE_CLIENT_PROOF_PATH", "")
    return Path(override) if override else _DEFAULT_EVIDENCE_PATH


def source_fingerprint() -> dict[str, str]:
    """SHA-256 of each proven client source as it exists on disk right now."""
    prints: dict[str, str] = {}
    for rel in PROVEN_SOURCES:
        path = _ROOT / rel
        try:
            prints[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            prints[rel] = ""
    return prints


def _stat_key() -> tuple:
    parts: list[Any] = []
    for path in (evidence_path(), *(_ROOT / rel for rel in PROVEN_SOURCES)):
        try:
            stat = path.stat()
            parts.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((str(path), None, None))
    return tuple(parts)


def _pending(reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": BROWSER_PROOF_PENDING, "reason": reason, "verified": False, **extra}


def _resolve() -> dict[str, Any]:
    path = evidence_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return _pending(
            "no_evidence_recorded",
            detail=(
                "Run scripts/verify_client_offline_endurance.py --write-evidence "
                "on a machine with Chrome to record the client proof."
            ),
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _pending("unreadable_evidence", detail="Proof artifact is not valid JSON.")
    if not isinstance(payload, dict):
        return _pending("unreadable_evidence", detail="Proof artifact is not an object.")

    if payload.get("result") != "pass":
        return _pending(
            "harness_failed",
            detail="The recorded harness run did not pass every leg.",
            recorded_at=payload.get("generated_at", ""),
        )

    legs = payload.get("legs")
    legs = legs if isinstance(legs, dict) else {}
    missing = [leg for leg in REQUIRED_LEGS if legs.get(leg) is not True]
    if missing:
        return _pending(
            "missing_legs",
            detail=f"Legs not proven: {', '.join(missing)}.",
            missing_legs=missing,
            recorded_at=payload.get("generated_at", ""),
        )

    recorded = payload.get("source_fingerprint")
    recorded = recorded if isinstance(recorded, dict) else {}
    current = source_fingerprint()
    drifted = sorted(
        rel for rel, digest in current.items() if recorded.get(rel) != digest or not digest
    )
    if drifted:
        return _pending(
            "source_changed_since_proof",
            detail=(
                "Client code changed after the proof was recorded — re-run the "
                f"harness. Changed: {', '.join(drifted)}."
            ),
            drifted_sources=drifted,
            recorded_at=payload.get("generated_at", ""),
        )

    return {
        "status": BROWSER_PROOF_VERIFIED,
        "reason": "verified",
        "verified": True,
        "detail": "Browser restart persistence and storage-pressure legs both proven.",
        "recorded_at": payload.get("generated_at", ""),
        "harness": payload.get("harness", ""),
    }


def browser_proof_detail() -> dict[str, Any]:
    """Resolved client-proof state, memoised on the evidence + source stats."""
    global _cache
    key = _stat_key()
    if _cache is not None and _cache[0] == key:
        return dict(_cache[1])
    resolved = _resolve()
    _cache = (key, resolved)
    return dict(resolved)


def browser_proof_status() -> str:
    """``BROWSER_PROOF_VERIFIED`` or ``PARTIAL_CLIENT_HARNESS_REQUIRED``."""
    return str(browser_proof_detail()["status"])


def reset_cache() -> None:
    """Drop the memoised resolution (tests that rewrite evidence in-place)."""
    global _cache
    _cache = None
