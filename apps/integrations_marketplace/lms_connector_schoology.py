"""v4.00.71 — Schoology LMS adapter scaffold (parallel to v4.00.70 D2L).

Adds the same 5 functions D2L exposes (oauth_authorize_url / refresh_token
/ push_grade / pull_courses / is_scaffold) plus an OAuth state-mint
helper used by the start-OAuth view.

Schoology API specifics (per Schoology Developer Docs):
* OAuth1 + REST API at ``https://api.schoology.com/v1/``
* OAuth2 isn't published; Schoology uses OAuth1 + 3-legged dance
* We expose an OAuth2 *style* authorize URL placeholder for the operator
  UI — the actual flow lands in a follow-up when the integration partner
  test instance is provisioned and the OAuth1 nonce/sig harness is wired.

State mint:
* ``mint_oauth_state(*, tenant_slug, user_pk, redirect_path) -> str``
  Returns a TimestampSigner-signed payload bound to the (tenant, user)
  pair. The state is consumed on callback to defend against CSRF +
  cross-account-binding attacks.
* ``read_oauth_state(raw) -> tuple[dict|None, reason]``
  5-state reason: ok / missing_token / expired_token / bad_token /
  malformed_payload.
"""
from __future__ import annotations

import logging
import urllib.parse as _ulib

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "schoology"
PROVIDER_LABEL = "Schoology"

# Schoology API surface roots (Apr 2026 snapshot).
DEFAULT_API_ROOT = "https://api.schoology.com/v1"
DEFAULT_AUTHORIZE_URL = "https://www.schoology.com/oauth/authorize"
DEFAULT_TOKEN_URL = "https://api.schoology.com/v1/oauth/access_token"

OAUTH_STATE_SALT = "rmc.lms.schoology.oauth_state.v4.00.71"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min


def oauth_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple = (),
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    """Build the Schoology authorize URL (OAuth2-shaped wrapper around the
    underlying OAuth1 flow; the consent-grant landing page accepts query
    parameters in the OAuth2 shape and bridges internally)."""
    qs = _ulib.urlencode([
        ("response_type", "code"),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("state", state),
        ("scope", " ".join(scopes) if scopes else "read write"),
    ])
    sep = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{sep}{qs}"


def mint_oauth_state(*, tenant_slug: str, user_pk: str | int,
                      redirect_path: str = "/") -> str:
    """Mint a CSRF-safe OAuth state. Payload format:
    ``"<tenant_slug>:<user_pk>:<redirect_path>"``.
    """
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    safe_redirect = redirect_path if redirect_path.startswith("/") and not redirect_path.startswith("//") else "/"
    payload = f"{tenant_slug}:{user_pk}:{safe_redirect}"
    return signer.sign(payload)


def read_oauth_state(raw: str):
    """Return ``(parsed_dict_or_None, reason)``.

    On success ``parsed_dict_or_None`` is ``{tenant_slug, user_pk, redirect_path}``.
    """
    from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    if not raw:
        return None, "missing_token"
    try:
        payload = signer.unsign(raw, max_age=OAUTH_STATE_TTL_SECONDS)
    except SignatureExpired:
        return None, "expired_token"
    except BadSignature:
        return None, "bad_token"
    parts = payload.split(":", 2)
    if len(parts) != 3:
        return None, "malformed_payload"
    return {"tenant_slug": parts[0], "user_pk": parts[1],
            "redirect_path": parts[2]}, "ok"


def refresh_token(*, refresh_token: str, client_id: str, client_secret: str) -> dict:
    """Honest-stub. Schoology uses OAuth1 long-lived tokens — no refresh
    in the OAuth2 sense. Production wiring lands in v4.00.71+."""
    logger.info("schoology.refresh_token: scaffold call (not wired)")
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "wave_landed": "v4.00.71"}


def push_grade(*, base_url: str, access_token: str, course_id: str,
               user_id: str, score: float, max_score: float,
               assignment_id: str = "", grade_id: str = "",
               comment: str = "") -> dict:
    """v4.00.75 — Honest-stub. Real wiring will POST to
    ``/sections/<id>/grades`` per Schoology REST API. This stub returns
    the *intended request shape* under ``would_send`` so calling code can
    unit-test their payload assembly without hitting the network.

    Validates inputs locally so operators get fast feedback on bad data:
      * score / max_score must be numeric and non-negative
      * score must not exceed max_score
      * course_id, user_id must be non-empty
    """
    # Local-only validation — surfaces operator bugs early.
    if not course_id or not user_id:
        return {"ok": False, "reason": "missing_required_field",
                "provider": PROVIDER_SLUG, "field": "course_id_or_user_id"}
    try:
        s = float(score)
        m = float(max_score)
    except (ValueError, TypeError):
        return {"ok": False, "reason": "score_not_numeric",
                "provider": PROVIDER_SLUG}
    if s < 0 or m <= 0:
        return {"ok": False, "reason": "score_out_of_range",
                "provider": PROVIDER_SLUG, "score": s, "max_score": m}
    if s > m:
        return {"ok": False, "reason": "score_exceeds_max",
                "provider": PROVIDER_SLUG, "score": s, "max_score": m}

    payload_shape = {
        "endpoint": f"{base_url.rstrip('/')}/sections/{course_id}/grades",
        "method": "PUT",
        "body": {
            "grades": {
                "grade": [{
                    "enrollment_id": user_id,
                    "assignment_id": assignment_id,
                    "grade_id": grade_id,
                    "grade": s,
                    "max_points": m,
                    "comment": comment,
                }]
            }
        },
    }
    logger.info("schoology.push_grade: scaffold call (would send %s)", payload_shape["endpoint"])
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "course_id": course_id, "user_id": user_id,
            "would_send": payload_shape}


def pull_courses(*, base_url: str, access_token: str) -> list[dict]:
    """Honest-stub. Real wiring walks /users/me/sections/."""
    logger.info("schoology.pull_courses: scaffold call (not wired)")
    return []


def is_scaffold() -> bool:
    return True
