"""Platform-wide non-repudiation action log (Wave E — year-end governance).

Any app records an administrative action with :func:`record_action`; entries form
a per-school SHA-256 hash chain and each carries an HMAC server signature, so a
later edit or re-ordering is detectable by :func:`verify_chain`. This is the
platform-wide complement to migration_cloud's domain-scoped audit chain.

The server signature proves the entry was written by RMC infrastructure and has
not been altered. Per-action *user presence* (WebAuthn) is a client ceremony; when
the caller has one, pass its id as ``webauthn_presence`` to bind it to the entry.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from django.conf import settings
from django.db import transaction

# payload keys we refuse to persist (defence-in-depth; callers pass summaries).
_SENSITIVE_KEYS = frozenset(
    {"password", "passwd", "pwd", "secret", "token", "api_key", "apikey", "private_key", "signature"}
)
_GENESIS = "genesis"


def _signing_key() -> bytes:
    raw = getattr(settings, "NON_REPUDIATION_SIGNING_KEY", "") or getattr(settings, "SECRET_KEY", "")
    return str(raw).encode("utf-8")


def _sanitize(payload: dict | None) -> dict:
    out: dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if str(key).lower() in _SENSITIVE_KEYS:
            continue
        out[str(key)] = value
    return out


def _canonical(*, sequence, action, resource, actor_id, school_id, payload, prev_hash) -> str:
    return json.dumps(
        {
            "sequence": sequence,
            "action": action,
            "resource": resource,
            "actor_id": actor_id,
            "school_id": str(school_id) if school_id is not None else None,
            "payload": payload,
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sign(integrity_hash: str) -> str:
    return hmac.new(_signing_key(), integrity_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def record_action(
    *,
    action: str,
    resource: str = "",
    actor_id=None,
    school_id=None,
    payload_summary: dict | None = None,
    webauthn_presence: str = "",
):
    """Append a signed, chained entry. Returns the persisted entry."""
    from apps.compliance.models import NonRepudiationLogEntry

    payload = _sanitize(payload_summary)
    with transaction.atomic():
        prev = (
            NonRepudiationLogEntry.objects.select_for_update()
            .filter(school_id=school_id)
            .order_by("-sequence")
            .first()
        )
        sequence = (prev.sequence + 1) if prev else 0
        prev_hash = prev.integrity_hash if prev else _GENESIS
        content = _canonical(
            sequence=sequence,
            action=str(action)[:80],
            resource=str(resource)[:255],
            actor_id=actor_id,
            school_id=school_id,
            payload=payload,
            prev_hash=prev_hash,
        )
        integrity_hash = _hash(content)
        entry = NonRepudiationLogEntry(
            school_id=school_id,
            sequence=sequence,
            actor_id=actor_id,
            action=str(action)[:80],
            resource=str(resource)[:255],
            payload_summary=payload,
            webauthn_presence=str(webauthn_presence or "")[:255],
            prev_hash=prev_hash,
            integrity_hash=integrity_hash,
            signature=_sign(integrity_hash),
        )
        entry.save()
    return entry


def verify_chain(school_id=None) -> dict[str, Any]:
    """Walk a school's chain; verify hash linkage + signature on every entry."""
    from apps.compliance.models import NonRepudiationLogEntry

    entries = list(
        NonRepudiationLogEntry.objects.filter(school_id=school_id).order_by("sequence")
    )
    prev_hash = _GENESIS
    checked = 0
    for entry in entries:
        content = _canonical(
            sequence=entry.sequence,
            action=entry.action,
            resource=entry.resource,
            actor_id=entry.actor_id,
            school_id=school_id,
            payload=entry.payload_summary,
            prev_hash=prev_hash,
        )
        if _hash(content) != entry.integrity_hash:
            return {"ok": False, "broken_at": entry.sequence, "reason": "hash mismatch", "checked": checked}
        if not hmac.compare_digest(_sign(entry.integrity_hash), entry.signature):
            return {"ok": False, "broken_at": entry.sequence, "reason": "signature mismatch", "checked": checked}
        prev_hash = entry.integrity_hash
        checked += 1
    return {"ok": True, "checked": checked}
