"""v4.00.82 — Itslearning LMS connector scaffold (HONEST stub; not OAUTH_READY).

Itslearning is a Norwegian K-12 + higher-ed LMS popular in Nordics +
UK + Germany. Uses OAuth 2.0 with per-region host
(e.g. https://elev.itslearning.com)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "itslearning"
PROVIDER_LABEL = "Itslearning"

# Itslearning's OAuth 2.0 endpoints are cloud-hosted at a stable origin
# (unlike Sakai/Blackboard/PowerSchool, which are per-instance). Per
# Itslearning Developer Docs (developer.itslearning.com).
DEFAULT_AUTHORIZE_URL = "https://oauth.itslearning.com/Oauth2/Authorize"
DEFAULT_TOKEN_URL = "https://oauth.itslearning.com/Oauth2/Token"
# Itslearning's coarse-grained scope grammar.
DEFAULT_SCOPES = ("Site.Read", "Site.Write")

# v4.00.82 — OAuth state mint TimestampSigner salt + TTL.
OAUTH_STATE_SALT = "rmc.lms.itslearning.oauth_state.v4.00.82"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min

# Honest declaration — surfaced via ``lms_supported_providers`` and the
# diagnostics dashboard's "Scaffold (coming soon)" pill.
IS_SCAFFOLD = True


def mint_oauth_state(*, client_id: str, return_to: str, nonce: str = "") -> str:
    """v4.00.82 — Mint a CSRF-safe OAuth state signed w/ TimestampSigner.

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
    """v4.00.82 — Return ``(payload_or_None, reason)``. 5-state taxonomy.

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
    """v4.00.82 — Honest-stub. Real wiring will POST
    ``/restapi/personal/grades/Save/<course_id>/<assignment_id>/<student_id>/v1``
    per Itslearning REST API docs. This stub returns the *intended request
    shape* under ``target_method`` / ``target_path_suffix`` / ``body`` so
    calling code can unit-test their payload assembly without hitting the
    network.

    Mirror of Blackboard / D2L / Schoology / PowerSchool / Sakai scaffold
    contract: validates required fields and returns
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

    # Itslearning REST API: POST
    # /restapi/personal/grades/Save/<course_id>/<assignment_id>/<student_id>/v1
    course_id = course_external_id
    assignment_id = assignment_external_id
    student_id = student_external_id
    target_path_suffix = (
        f"/restapi/personal/grades/Save/{course_id}/{assignment_id}/{student_id}/v1"
    )
    body = {
        "student_external_id": student_external_id,
        "score": score,
        "max_score": max_score,
        "comment": "",
    }
    logger.info(
        "itslearning.push_grade: scaffold call (would POST %s, dry_run=%s)",
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
