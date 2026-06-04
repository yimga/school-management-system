"""v4.00.91 Studio-OS-10X W1 Pillar B10 — ClassLink roster connector scaffold.

ClassLink is a US K-12 SSO + rostering platform (competitor to Clever).
OAuth 2.0 via ``https://launchpad.classlink.com/oauth2/`` with tenant-
scoped tokens. Roster pulls hit ``https://nodeapi.classlink.com/`` (OneRoster
v1.1 compatible) for orgs/users/classes/enrollments.

NOTE: ClassLink, like Clever, is a roster IdP, not a grade-pushing LMS.
:func:`push_grade` returns ``provider_does_not_accept_grades`` so callers
branch correctly.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "classlink"
PROVIDER_LABEL = "ClassLink"

DEFAULT_AUTHORIZE_URL = "https://launchpad.classlink.com/oauth2/v2/auth"
DEFAULT_TOKEN_URL = "https://launchpad.classlink.com/oauth2/v2/token"
DEFAULT_API_BASE = "https://nodeapi.classlink.com"
# ClassLink scope grammar — fine-grained roster scopes per OneRoster category.
DEFAULT_SCOPES = ("oneroster", "profile", "openid")

OAUTH_STATE_SALT = "rmc.lms.classlink.oauth_state.v4.00.91"
OAUTH_STATE_TTL_SECONDS = 600  # magic-number-allow: ttl-seconds

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


def pull_roster_users(*, tenant_id: str, role: str = "student", dry_run: bool = True) -> dict:
    """Honest scaffold — ClassLink's OneRoster-compatible user pull shape."""
    if not tenant_id:
        return {"reason": "missing_field", "field": "tenant_id", "scaffold": True}
    if role not in {"student", "teacher", "administrator"}:
        return {"reason": "bad_role", "field": "role", "received": role, "scaffold": True}
    target_path_suffix = f"/v2/{tenant_id}/{role}s"
    logger.info(
        "classlink.pull_roster_users: scaffold call (would GET %s, dry_run=%s)",
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
    """ClassLink does not accept grade pushes — it's a roster IdP only."""
    return {
        "reason": "provider_does_not_accept_grades",
        "provider": PROVIDER_SLUG,
        "note": "ClassLink is a roster identity provider; grade-pass-back happens through downstream LMS.",
        "scaffold": True,
    }
