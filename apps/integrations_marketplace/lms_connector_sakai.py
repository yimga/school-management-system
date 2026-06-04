"""v4.00.81 — Sakai LMS connector scaffold (HONEST stub; not OAUTH_READY).

Sakai is the Apereo Foundation open-source LMS (sakai.apereo.org).
Its OAuth/OIDC integration via LTI 1.3 + Sakai-Web-Services REST API
has per-instance host (e.g. https://lms.university.edu/sakai/)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "sakai"
PROVIDER_LABEL = "Sakai"

# Sakai is per-instance (like Blackboard / Canvas / PowerSchool) — endpoints
# are SUFFIXES of the operator-supplied per-tenant base_url, not absolute
# hosts. Per Sakai OAuth docs (sakai.apereo.org/oauth-tool/).
DEFAULT_AUTHORIZE_URL_SUFFIX = "/oauth-tool/rest/oauth/authorize"
DEFAULT_TOKEN_URL_SUFFIX = "/oauth-tool/rest/oauth/token"
# Sakai's REST API scope grammar.
DEFAULT_SCOPES = ("sakai:read", "sakai:write")

# v4.00.81 — OAuth state mint TimestampSigner salt + TTL.
OAUTH_STATE_SALT = "rmc.lms.sakai.oauth_state.v4.00.81"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min  # magic-number-allow: ttl-seconds

# Honest declaration — surfaced via ``lms_supported_providers`` and the
# diagnostics dashboard's "Scaffold (coming soon)" pill.
IS_SCAFFOLD = True


def mint_oauth_state(*, client_id: str, return_to: str, nonce: str = "") -> str:
    """v4.00.81 — Mint a CSRF-safe OAuth state signed w/ TimestampSigner.

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
    """v4.00.81 — Return ``(payload_or_None, reason)``. 5-state taxonomy.

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
    """v4.00.81 — Honest-stub. Real wiring will PUT
    ``/direct/gradebook/<course_id>/item/<assignment_id>/score/<student_id>``
    per Sakai Web Services REST API docs. This stub returns the *intended
    request shape* under ``target_method`` / ``target_path_suffix`` / ``body``
    so calling code can unit-test their payload assembly without hitting the
    network.

    Mirror of Blackboard / D2L / Schoology / PowerSchool scaffold contract:
    validates required fields and returns
    ``{reason: "missing_field", field: "<name>"}`` on failure so callers can
    rely on identical error-shape taxonomy across providers.
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

    # Sakai Web Services REST API: PUT
    # /direct/gradebook/<course_id>/item/<assignment_id>/score/<student_id>
    target_path_suffix = (
        f"/direct/gradebook/{course_external_id}"
        f"/item/{assignment_external_id}"
        f"/score/{student_external_id}"
    )
    body = {
        "student_external_id": student_external_id,
        "score": score,
        "max_score": max_score,
        "comment": "",
    }
    logger.info(
        "sakai.push_grade: scaffold call (would PUT %s, dry_run=%s)",
        target_path_suffix, dry_run,
    )
    return {
        "would_send": True,
        "target_method": "PUT",
        "target_path_suffix": target_path_suffix,
        "body": body,
        "scaffold": True,
        "reason": "scaffold_no_outbound_http",
    }


# ---------------------------------------------------------------------------
# v4.00.91 Studio-OS-10X W1 Pillar B3 — Promotion to OAUTH_READY tier.
# Live outbound gated behind RMC_SAKAI_OAUTH_LIVE_OUTBOUND env.
# ---------------------------------------------------------------------------
IS_SCAFFOLD = False  # B3 promotion v4.00.91

from apps.integrations_marketplace.lms_oauth_ready_helpers import make_oauth_ready_helpers as _make
_helpers = _make(
    provider_slug="sakai",
    live_env_var="RMC_SAKAI_OAUTH_LIVE_OUTBOUND",
    token_url=DEFAULT_TOKEN_URL_SUFFIX,
    grade_push_path_builder=lambda c, a, s: f"/direct/gradebook/{c}/{a}/{s}",
    grade_push_method="POST",
)
exchange_authorization_code_for_token = _helpers["exchange"]
refresh_access_token = _helpers["refresh"]
push_grade_live = _helpers["push_grade_live"]
