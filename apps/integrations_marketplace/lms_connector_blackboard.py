"""v4.00.79 — Blackboard Learn LMS connector scaffold (HONEST stub; not OAUTH_READY).

Honest-stub adapter parallel to D2L (v4.00.70) and Schoology (v4.00.69) —
registered in ``lms_supported_providers.SCAFFOLD_LMS_PROVIDERS`` but NOT in
the OAuth-ready set yet. The functions here are import-stable and have the
correct return shape contracts so calling code can be written against them;
production wiring (real HTTP calls, OAuth exchange) lands in a follow-up
wave once the integration partner test instance is provisioned.

Blackboard Learn API specifics (per Blackboard Learn REST API docs):

* Blackboard Learn is a per-instance LMS (district-owned host like Canvas)
  rather than a single SaaS endpoint — every tenant has its own base URL
  (e.g. ``https://<institution>.blackboard.com``). The OAuth2 authorize +
  token endpoints are suffix paths on that base URL, NOT absolute hosts.
* OAuth2 authorize suffix: ``/learn/api/public/v1/oauth2/authorizationcode``
* OAuth2 token suffix:     ``/learn/api/public/v1/oauth2/token``
* Default scopes: ``read write delete`` (Blackboard REST API tri-scope set).

State mint mirrors the D2L / Schoology pattern (5-state reason taxonomy)
so callers get identical error-shape contracts across all 3 scaffolds.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "blackboard"
PROVIDER_LABEL = "Blackboard Learn"

# Blackboard Learn is per-instance (like Canvas) — endpoints are SUFFIXES
# of the operator-supplied base_url, not absolute hosts.
DEFAULT_AUTHORIZE_URL_SUFFIX = "/learn/api/public/v1/oauth2/authorizationcode"
DEFAULT_TOKEN_URL_SUFFIX = "/learn/api/public/v1/oauth2/token"
DEFAULT_SCOPES = ("read", "write", "delete")

# v4.00.79 — OAuth state mint TimestampSigner salt + TTL.
OAUTH_STATE_SALT = "rmc.lms.blackboard.oauth_state.v4.00.79"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min  # magic-number-allow: ttl-seconds

# Honest declaration — surfaced via ``lms_supported_providers`` and the
# diagnostics dashboard's "Scaffold (coming soon)" pill.
IS_SCAFFOLD = True


def mint_oauth_state(*, client_id: str, return_to: str, nonce: str = "") -> str:
    """v4.00.79 — Mint a CSRF-safe OAuth state signed w/ TimestampSigner.

    Payload format: ``"<client_id>:<return_to>:<nonce>"``.
    Open-redirect defense: ``return_to`` must start with "/" not "//".
    """
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    safe_return_to = (
        return_to
        if return_to.startswith("/") and not return_to.startswith("//")
        else "/"
    )
    payload = f"{client_id}:{safe_return_to}:{nonce}"
    return signer.sign(payload)


def read_oauth_state(token: str) -> tuple[dict | None, str]:
    """v4.00.79 — Return ``(payload_or_None, reason)``. 5-state taxonomy.

    Reasons: ``ok / missing_token / expired_token / bad_token / malformed_payload``.

    On success ``payload_or_None`` is ``{client_id, return_to, nonce}``.
    """
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
    return {
        "client_id": parts[0],
        "return_to": parts[1],
        "nonce": parts[2],
    }, "ok"


def push_grade(
    *,
    student_external_id: str,
    course_external_id: str,
    assignment_external_id: str,
    score: float,
    max_score: float,
    dry_run: bool = True,
) -> dict:
    """v4.00.79 — Honest-stub. Real wiring will PATCH
    ``/learn/api/public/v1/courses/<courseId>/gradebook/columns/<columnId>/users/<userId>``
    per Blackboard Learn REST docs. This stub returns the *intended request
    shape* under ``target_method`` / ``target_path_suffix`` / ``body`` so
    calling code can unit-test their payload assembly without hitting the
    network.

    Mirror of D2L / Schoology scaffold contract: validates required fields
    and returns ``{reason: "missing_field", field: "<name>"}`` on failure
    so callers can rely on identical error-shape taxonomy across providers.
    """
    if not student_external_id:
        return {"reason": "missing_field", "field": "student_external_id",
                "scaffold": True}
    if not course_external_id:
        return {"reason": "missing_field", "field": "course_external_id",
                "scaffold": True}
    if not assignment_external_id:
        return {"reason": "missing_field", "field": "assignment_external_id",
                "scaffold": True}

    # Blackboard Learn API: PATCH
    # /learn/api/public/v1/courses/<courseId>/gradebook/columns/<columnId>/users/<userId>
    target_path_suffix = (
        f"/learn/api/public/v1/courses/{course_external_id}"
        f"/gradebook/columns/{assignment_external_id}"
        f"/users/{student_external_id}"
    )
    body = {
        "score": score,
        "possible": max_score,
        "text": "",
        "notes": "",
        "feedback": "",
    }
    logger.info(
        "blackboard.push_grade: scaffold call (would PATCH %s, dry_run=%s)",
        target_path_suffix, dry_run,
    )
    return {
        "would_send": True,
        "target_method": "PATCH",
        "target_path_suffix": target_path_suffix,
        "body": body,
        "scaffold": True,
        "reason": "scaffold_no_outbound_http",
    }


# ---------------------------------------------------------------------------
# v4.00.91 Studio-OS-10X W1 Pillar B1 — Promotion to OAUTH_READY tier.
# Adds exchange_authorization_code_for_token / refresh_access_token /
# push_grade_live following the v4.00.83 Schoology pattern. Live outbound
# gated behind RMC_BLACKBOARD_OAUTH_LIVE_OUTBOUND env. Dry-run mode returns
# the intended HTTP request shape under ``would_send``.
# ---------------------------------------------------------------------------
IS_SCAFFOLD = False  # B1 promotion v4.00.91

from apps.integrations_marketplace.lms_oauth_ready_helpers import make_oauth_ready_helpers as _make
_helpers = _make(
    provider_slug="blackboard",
    live_env_var="RMC_BLACKBOARD_OAUTH_LIVE_OUTBOUND",
    token_url=DEFAULT_TOKEN_URL_SUFFIX,
    grade_push_path_builder=lambda c, a, s: f"/learn/api/public/v2/courses/{c}/gradebook/columns/{a}/users/{s}",
    grade_push_method="PATCH",
)
exchange_authorization_code_for_token = _helpers["exchange"]
refresh_access_token = _helpers["refresh"]
push_grade_live = _helpers["push_grade_live"]
