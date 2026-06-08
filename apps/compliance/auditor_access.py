"""Auditor magic-link service (Wave E — year-end governance).

Operators mint a time-bounded, revocable, PII-masked, access-logged grant for an
external inspector. The magic link carries a ``TimestampSigner`` token over the
grant id (reusing the platform's reports.share token pattern) — the inspector
never logs in; the unexpired, unrevoked grant is the authorisation, and the view
only ever exposes masked, read-only data via ``compliance.pii_masking``.

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave E) and register row ``auditor-magic-link``.
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import timedelta
from typing import Any

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

logger = logging.getLogger(__name__)

_SIGNER_SALT = "auditor.inspector"
_DEFAULT_TTL_HOURS = 72
# Signer max_age is a coarse outer guard; expires_at is the source of truth.
_TOKEN_MAX_AGE_DAYS = 365  # magic-number-allow: one-year outer token-age guard


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=_SIGNER_SALT)


def normalize_ip_allowlist(entries) -> list[str]:
    """Validate + canonicalise IP/CIDR entries; drop anything unparseable.

    Accepts a list, or a comma/newline/space-separated string. Each surviving
    entry is a canonical ``str`` of an :class:`ipaddress.ip_network` (a bare host
    becomes a /32 or /128). Invalid tokens are dropped (logged, never raised) so a
    typo can never silently widen access — it just won't match.
    """
    if isinstance(entries, str):
        raw = entries.replace(",", "\n").split()
    else:
        raw = list(entries or [])
    out: list[str] = []
    for token in raw:
        text = str(token or "").strip()
        if not text:
            continue
        try:
            net = ipaddress.ip_network(text, strict=False)
        except ValueError:
            logger.info("auditor allowlist: dropping unparseable entry")
            continue
        canonical = str(net)
        if canonical not in out:
            out.append(canonical)
    return out


def ip_is_allowed(grant, ip_address: str | None) -> bool:
    """True if ``ip_address`` satisfies the grant's geo-fence.

    An EMPTY allowlist means "no IP restriction" (opt-in enforcement → backwards
    compatible). A non-empty allowlist with a missing/unparseable client IP is a
    DENY (fail-closed): if a grant is geo-fenced we refuse access we cannot place.
    """
    allowlist = normalize_ip_allowlist(getattr(grant, "ip_allowlist", None) or [])
    if not allowlist:
        return True
    if not ip_address:
        return False
    try:
        client = ipaddress.ip_address(str(ip_address).strip())
    except ValueError:
        return False
    for entry in allowlist:
        try:
            if client in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:  # pragma: no cover - normalize_ip_allowlist already filtered
            continue
    return False


def create_grant(
    *,
    school_id,
    inspector_email: str = "",
    inspector_label: str = "",
    created_by_id=None,
    ttl_hours: int = _DEFAULT_TTL_HOURS,
    scope: list[str] | None = None,
    note: str = "",
    ip_allowlist=None,
) -> tuple[Any, str]:
    """Create a grant + return (grant, magic_token). Token encodes the grant id."""
    from apps.compliance.models import AuditorAccessGrant

    hours = max(1, int(ttl_hours or _DEFAULT_TTL_HOURS))
    grant = AuditorAccessGrant.objects.create(
        school_id=school_id,
        inspector_email=(inspector_email or "").strip(),
        inspector_label=(inspector_label or "").strip()[:120],
        created_by_id=created_by_id,
        scope=list(scope or ["students:read"]),
        ip_allowlist=normalize_ip_allowlist(ip_allowlist or []),
        note=(note or "").strip()[:255],
        expires_at=timezone.now() + timedelta(hours=hours),
    )
    token = _signer().sign(str(grant.id))
    return grant, token


def resolve_grant(token: str):
    """Return a valid grant for a token, or None (bad sig / expired / revoked)."""
    from apps.compliance.models import AuditorAccessGrant

    raw = (token or "").strip()
    if not raw:
        return None
    try:
        # max_age guards even if expires_at drifts; expires_at is the source of truth.
        grant_id = _signer().unsign(raw, max_age=timedelta(days=_TOKEN_MAX_AGE_DAYS))
    except (BadSignature, SignatureExpired):
        return None
    grant = AuditorAccessGrant.objects.filter(pk=grant_id).first()  # tenant-isolation-allow: pk-lookup-signed-grant-operator-only
    if grant is None or not grant.is_valid():
        return None
    return grant


def revoke_grant(grant_id) -> bool:
    from apps.compliance.models import AuditorAccessGrant

    grant = AuditorAccessGrant.objects.filter(pk=grant_id).first()  # tenant-isolation-allow: pk-revoke-signed-grant-operator-only
    if grant is None or grant.is_revoked:
        return False
    grant.is_revoked = True
    grant.revoked_at = timezone.now()
    grant.save(update_fields=["is_revoked", "revoked_at"])
    return True


def log_access(
    grant,
    resource: str,
    ip_address: str | None = None,
    *,
    allowed: bool = True,
    denied_reason: str = "",
) -> None:
    from apps.compliance.models import AuditorAccessLog

    AuditorAccessLog.objects.create(
        grant=grant,
        resource=str(resource or "")[:255],
        ip_address=ip_address or None,
        allowed=bool(allowed),
        denied_reason=str(denied_reason or "")[:64],
    )


def masked_roster_for_grant(grant, *, limit: int = 500) -> list[dict[str, Any]]:
    """PII-masked, read-only student roster the inspector may view."""
    from apps.compliance.pii_masking import mask_roster_for_auditor
    from apps.people.models import StudentProfile

    students = StudentProfile.objects.filter(school_id=grant.school_id).order_by("last_name")[
        : max(1, int(limit))
    ]
    return mask_roster_for_auditor(students)
