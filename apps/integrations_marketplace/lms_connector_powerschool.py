"""v4.00.80 — PowerSchool LMS connector scaffold (HONEST stub; not OAUTH_READY).

PowerSchool (formerly Schoology Enterprise — the K-12 SIS + LMS hybrid)
uses OAuth 2.0 client-credentials per-instance. Endpoints are per-tenant
host (e.g. https://district.powerschool.com)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "powerschool"
PROVIDER_LABEL = "PowerSchool Learning"

# PowerSchool is per-instance (like Blackboard / Canvas) — endpoints are
# SUFFIXES of the operator-supplied per-tenant base_url, not absolute hosts.
DEFAULT_AUTHORIZE_URL_SUFFIX = "/oauth/authorize"
DEFAULT_TOKEN_URL_SUFFIX = "/oauth/token"
# PowerSchool's REST API scope grammar.
DEFAULT_SCOPES = ("rest:read", "rest:write")

# v4.00.80 — OAuth state mint TimestampSigner salt + TTL.
OAUTH_STATE_SALT = "rmc.lms.powerschool.oauth_state.v4.00.80"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min  # magic-number-allow: ttl-seconds

# Honest declaration — surfaced via ``lms_supported_providers`` and the
# diagnostics dashboard's "Scaffold (coming soon)" pill.
IS_SCAFFOLD = True


def mint_oauth_state(*, client_id: str, return_to: str, nonce: str = "") -> str:
    """v4.00.80 — Mint a CSRF-safe OAuth state signed w/ TimestampSigner.

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
    """v4.00.80 — Return ``(payload_or_None, reason)``. 5-state taxonomy.

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
    """v4.00.80 — Honest-stub. Real wiring will POST
    ``/ws/v1/school/<sid>/assignment/<aid>/section_assignment_grade``
    per PowerSchool REST API docs. This stub returns the *intended request
    shape* under ``target_method`` / ``target_path_suffix`` / ``body`` so
    calling code can unit-test their payload assembly without hitting the
    network.

    Mirror of Blackboard / D2L / Schoology scaffold contract: validates
    required fields and returns ``{reason: "missing_field", field: "<name>"}``
    on failure so callers can rely on identical error-shape taxonomy across
    providers.
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

    # PowerSchool REST API: POST
    # /ws/v1/school/<sid>/assignment/<aid>/section_assignment_grade
    target_path_suffix = (
        f"/ws/v1/school/{course_external_id}"
        f"/assignment/{assignment_external_id}"
        f"/section_assignment_grade"
    )
    body = {
        "student_external_id": student_external_id,
        "score": score,
        "max_score": max_score,
        "comment": "",
    }
    logger.info(
        "powerschool.push_grade: scaffold call (would POST %s, dry_run=%s)",
        target_path_suffix, dry_run,
    )
    return {
        "would_send": True,
        "target_method": "POST",
        "target_path_suffix": target_path_suffix,
        "body": body,
        "scaffold": True,
        "reason": "scaffold_no_outbound_http",
    }


# ---------------------------------------------------------------------------
# v4.00.91 Studio-OS-10X W1 Pillar B2 — Promotion to OAUTH_READY tier.
# Live outbound gated behind RMC_POWERSCHOOL_OAUTH_LIVE_OUTBOUND env.
# ---------------------------------------------------------------------------
IS_SCAFFOLD = False  # B2 promotion v4.00.91

from apps.integrations_marketplace.lms_oauth_ready_helpers import make_oauth_ready_helpers as _make
_helpers = _make(
    provider_slug="powerschool",
    live_env_var="RMC_POWERSCHOOL_OAUTH_LIVE_OUTBOUND",
    token_url=DEFAULT_TOKEN_URL_SUFFIX,
    grade_push_path_builder=lambda c, a, s: f"/ws/v1/assignment/{a}/student/{s}/score",
    grade_push_method="PUT",
)
exchange_authorization_code_for_token = _helpers["exchange"]
refresh_access_token = _helpers["refresh"]
push_grade_live = _helpers["push_grade_live"]
