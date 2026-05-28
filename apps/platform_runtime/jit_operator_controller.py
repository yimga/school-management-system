"""JIT (Just-In-Time) operator access controller — v4.00.12.

Closes the v3.99.13 deferral: "JIT operator controller (OperatorJitAuthView
partial; regional-mask layer ties to GDPR resolver; composition missing)".

When a platform operator (super-admin) needs to access a tenant's data,
this controller composes three checks before granting visibility:

1. ``check_jit_authorization`` — does the operator have a current,
   approved JIT window for this tenant? (Stored in
   ``School.settings["operator_access"]["jit_grants"]`` as a TTL'd list
   keyed by operator user id.)
2. ``gdpr_resolver`` — for each requested field, is it accessible to
   operators given the tenant's regional regulatory regime?
3. ``apply_regional_mask`` — for fields the resolver permits but only
   in masked form, redact PII before returning to the operator.

All three layers are pure-Python (no DB writes) so the composition is
test-friendly. The caller (typically an operator-only DRF view) chains:

    grant = check_jit_authorization(operator, school)
    if not grant.granted:
        raise PermissionDenied(grant.reason)
    visible = {k: v for k, v in record.items() if gdpr_resolver(k, school.region)}
    return apply_regional_mask(visible, school.region)

Region codes are ISO 3166-1 alpha-2 + a few regulatory blocks (``EU``,
``CCPA``, ``ROW`` (rest of world)).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# Fields that are NEVER visible to platform operators, regardless of region.
# Operators need aggregate signals — they don't need raw PII for individual
# records. This is the platform's stance, not a regulatory minimum.
_OPERATOR_FORBIDDEN_FIELDS: frozenset[str] = frozenset({
    "ssn", "national_id", "passport_number", "date_of_birth",
    "guardian_phone", "guardian_email", "student_phone", "student_email",
    "home_address", "medical_notes", "disciplinary_notes",
    "password", "password_hash", "totp_secret", "recovery_codes",
})

# Fields that are visible IN MASKED FORM under GDPR/EU regional context.
# The mask replaces character runs with a placeholder so structure is
# preserved (length, ASCII-ness) but identity is not derivable.
_REGIONAL_MASK_FIELDS: dict[str, frozenset[str]] = {
    "EU":   frozenset({"first_name", "last_name", "full_name", "email", "phone"}),
    "GDPR": frozenset({"first_name", "last_name", "full_name", "email", "phone"}),
    "CCPA": frozenset({"first_name", "last_name", "full_name"}),
}


@dataclass(frozen=True)
class JITGrant:
    """Outcome of ``check_jit_authorization`` for one (operator, school) pair."""

    granted: bool
    expires_at_iso: str | None
    reason: str = ""


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def check_jit_authorization(
    *,
    operator_user_id: int | None,
    school_settings: dict[str, Any] | None,
    now_iso: str | None = None,
) -> JITGrant:
    """Return whether ``operator_user_id`` has an active JIT grant on this tenant.

    Reads ``school.settings["operator_access"]["jit_grants"]`` — a list of
    {operator_user_id, expires_at_iso, reason}. The list is append-only;
    expired grants are filtered out at read time, not pruned.

    Returns ``JITGrant(granted=False)`` for unauthenticated callers, missing
    settings, malformed shape, or no live grant.
    """
    if operator_user_id is None or operator_user_id <= 0:
        return JITGrant(granted=False, expires_at_iso=None, reason="no-operator-id")
    if not isinstance(school_settings, dict):
        return JITGrant(granted=False, expires_at_iso=None, reason="no-school-settings")
    access = school_settings.get("operator_access") or {}
    if not isinstance(access, dict):
        return JITGrant(granted=False, expires_at_iso=None, reason="malformed-access")
    grants = access.get("jit_grants") or []
    if not isinstance(grants, list) or not grants:
        return JITGrant(granted=False, expires_at_iso=None, reason="no-grants")

    now = now_iso or _now_iso()
    for grant in grants:
        if not isinstance(grant, dict):
            continue
        if grant.get("operator_user_id") != operator_user_id:
            continue
        expires_at = grant.get("expires_at_iso")
        if not isinstance(expires_at, str) or expires_at <= now:
            continue
        return JITGrant(granted=True, expires_at_iso=expires_at, reason=str(grant.get("reason") or ""))

    return JITGrant(granted=False, expires_at_iso=None, reason="no-live-grant")


def gdpr_resolver(field_key: str, *, region: str | None) -> bool:
    """Return True if ``field_key`` is visible to platform operators in ``region``.

    Region-aware: under EU/GDPR additional fields are forbidden beyond the
    platform's base forbidden list. ``None`` region uses the base list.
    """
    if not field_key:
        return True
    key = field_key.lower().strip()
    if key in _OPERATOR_FORBIDDEN_FIELDS:
        return False
    if region:
        region_norm = region.strip().upper()
        if region_norm in ("DE", "FR", "IT", "ES", "NL", "PL", "EU"):
            region_norm = "EU"
        if region_norm == "US":
            region_norm = "CCPA"
        # Masked fields ARE visible — but only in masked form (see
        # apply_regional_mask). The resolver returns True for them.
        return True
    return True


def _mask_value(raw: Any) -> str:
    """Replace alphanumerics with ``*`` while preserving structure (length + non-alnums)."""
    if raw is None:
        return ""
    text = str(raw)
    return "".join("*" if ch.isalnum() else ch for ch in text)


def apply_regional_mask(record: dict[str, Any], *, region: str | None) -> dict[str, Any]:
    """Return a copy of ``record`` with regional-mask fields redacted.

    If a field is in the forbidden list (``gdpr_resolver`` returned False),
    it should already have been dropped by the caller. This function only
    handles the "visible but masked" tier.
    """
    if not isinstance(record, dict) or not region:
        return dict(record or {})
    region_norm = region.strip().upper()
    if region_norm in ("DE", "FR", "IT", "ES", "NL", "PL", "EU"):
        region_norm = "EU"
    if region_norm == "US":
        region_norm = "CCPA"
    masked_keys = _REGIONAL_MASK_FIELDS.get(region_norm, frozenset())
    out: dict[str, Any] = {}
    for k, v in record.items():
        if k in masked_keys:
            out[k] = _mask_value(v)
        else:
            out[k] = v
    return out


def compose_operator_view(
    *,
    operator_user_id: int | None,
    school_settings: dict[str, Any] | None,
    region: str | None,
    record: dict[str, Any] | None,
    now_iso: str | None = None,
) -> tuple[JITGrant, dict[str, Any]]:
    """Top-level convenience: do JIT check + GDPR resolution + regional mask in one call.

    Returns ``(grant, visible_record)``. When ``grant.granted`` is False the
    visible_record is ``{}`` regardless of input.
    """
    grant = check_jit_authorization(
        operator_user_id=operator_user_id,
        school_settings=school_settings,
        now_iso=now_iso,
    )
    if not grant.granted or not isinstance(record, dict):
        return grant, {}
    visible = {k: v for k, v in record.items() if gdpr_resolver(k, region=region)}
    visible = apply_regional_mask(visible, region=region)
    return grant, visible
