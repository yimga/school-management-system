"""v4.00.91 Studio-OS-10X W1 Pillar B9 — Clever roster connector scaffold.

Clever is a US K-12 roster identity provider (not a grade-pushing LMS).
OAuth 2.0 via ``https://clever.com/oauth/`` with district-scoped tokens.
Roster pulls hit ``https://api.clever.com/v3.0/`` for sections/teachers/
students. This scaffold lays in the OAuth state machinery + a roster-pull
stub returning intended request shape.

NOTE: Clever does not accept grade pushes — :func:`push_grade` here
returns ``reason: "provider_does_not_accept_grades"`` rather than the
``would_send`` envelope so callers can branch correctly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "clever"
PROVIDER_LABEL = "Clever"

DEFAULT_AUTHORIZE_URL = "https://clever.com/oauth/authorize"
DEFAULT_TOKEN_URL = "https://clever.com/oauth/tokens"
DEFAULT_API_BASE = "https://api.clever.com/v3.0"
# Clever scope grammar is implicit — district-token grants are full-roster.
DEFAULT_SCOPES = ()

OAUTH_STATE_SALT = "rmc.lms.clever.oauth_state.v4.00.91"
OAUTH_STATE_TTL_SECONDS = 600

IS_SCAFFOLD = True


def mint_oauth_state(*, client_id: str, return_to: str, nonce: str = "") -> str:
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    safe_return_to = (
        return_to
        if return_to.startswith("/") and not return_to.startswith("//")
        else "/"
    )
    return signer.sign(f"{client_id}:{safe_return_to}:{nonce}")


def read_oauth_state(token: str) -> tuple[dict | None, str]:
    from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    if not token:
        return None, "missing_token"
    try:
        payload = signer.unsign(token, max_age=OAUTH_STATE_TTL_SECONDS)
    except SignatureExpired:
        return None, "expired_token"
    except BadSignature:
        return None, "bad_token"
    parts = payload.split(":", 2)
    if len(parts) != 3:
        return None, "malformed_payload"
    return {"client_id": parts[0], "return_to": parts[1], "nonce": parts[2]}, "ok"


def pull_roster_sections(*, district_id: str, dry_run: bool = True) -> dict:
    """Honest scaffold — Clever's roster sections endpoint shape."""
    if not district_id:
        return {"reason": "missing_field", "field": "district_id", "scaffold": True}
    target_path_suffix = f"/sections?district={district_id}"
    logger.info(
        "clever.pull_roster_sections: scaffold call (would GET %s, dry_run=%s)",
        target_path_suffix, dry_run,
    )
    return {
        "would_send": True,
        "target_method": "GET",
        "target_path_suffix": target_path_suffix,
        "scaffold": True,
        "reason": "scaffold_no_outbound_http",
    }


def push_grade(**kwargs) -> dict:
    """Clever does not accept grade pushes — it's a roster IdP only."""
    return {
        "reason": "provider_does_not_accept_grades",
        "provider": PROVIDER_SLUG,
        "note": "Clever is a roster identity provider; grade-pass-back happens through downstream LMS.",
        "scaffold": True,
    }
