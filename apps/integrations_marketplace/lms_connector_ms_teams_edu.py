"""v4.00.91 Studio-OS-10X W1 Pillar B8 — Microsoft Teams Education scaffold.

Microsoft Teams for Education uses Microsoft Identity Platform (Entra ID,
formerly Azure AD) OAuth 2.0. Tenant-scoped endpoints under
``https://login.microsoftonline.com/<tenant>/oauth2/v2.0/`` with Graph API
calls to ``https://graph.microsoft.com/v1.0/education/``.

This module is a HONEST stub (not OAUTH_READY). It carries:
  * stable OAuth2 endpoint constants (tenant placeholder)
  * mint/read OAuth state (CSRF defense)
  * push_grade scaffold returning intended request shape under
    ``target_method`` / ``target_path_suffix`` / ``body`` so callers can
    unit-test payload assembly without hitting the network.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PROVIDER_SLUG = "ms_teams_edu"
PROVIDER_LABEL = "Microsoft Teams for Education"

# Microsoft Identity Platform v2.0 endpoints — tenant placeholder substituted
# at runtime by the OAuth start view. ``common`` works for multi-tenant apps
# but production tenants typically substitute their directory ID.
DEFAULT_AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize"
DEFAULT_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
# Education Graph scopes — read for roster pulls, write for grade pushes.
DEFAULT_SCOPES = (
    "https://graph.microsoft.com/EduRoster.Read",
    "https://graph.microsoft.com/EduAssignments.ReadWrite",
)

OAUTH_STATE_SALT = "rmc.lms.ms_teams_edu.oauth_state.v4.00.91"
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


def push_grade(
    *,
    student_external_id: str,
    course_external_id: str,
    assignment_external_id: str,
    score: float,
    max_score: float,
    dry_run: bool = True,
) -> dict:
    """Honest scaffold — returns intended Graph API call shape.

    Real call: PATCH
    /education/classes/{class_id}/assignments/{assignment_id}/submissions/{submission_id}
    with feedback + points body.
    """
    if not student_external_id:
        return {"reason": "missing_field", "field": "student_external_id", "scaffold": True}
    if not course_external_id:
        return {"reason": "missing_field", "field": "course_external_id", "scaffold": True}
    if not assignment_external_id:
        return {"reason": "missing_field", "field": "assignment_external_id", "scaffold": True}

    target_path_suffix = (
        f"/v1.0/education/classes/{course_external_id}"
        f"/assignments/{assignment_external_id}"
        f"/submissions/{student_external_id}/setUpReturn"
    )
    body = {
        "feedback": {"text": {"content": "", "contentType": "text"}},
        "points": {"points": score, "outOfPoints": max_score},
    }
    logger.info(
        "ms_teams_edu.push_grade: scaffold call (would PATCH %s, dry_run=%s)",
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
