"""v4.00.70 — Brightspace (D2L) LMS adapter scaffold.

Honest-stub adapter parallel to Schoology (v4.00.69) — registered in
``lms_supported_providers.SCAFFOLD_LMS_PROVIDERS`` but NOT in the
OAuth-ready set yet. The functions here are import-stable and have the
correct return shape contracts so calling code can be written against
them; production wiring (real HTTP calls, OAuth exchange) lands in a
follow-up wave once the integration partner test instance is provisioned.

Public surface (mirrors ``apps.api.lms_adapters`` for canvas/moodle/google):

  * ``oauth_authorize_url(*, client_id, redirect_uri, state, scopes=()) -> str``
  * ``refresh_token(*, refresh_token, client_id, client_secret) -> dict``
  * ``push_grade(*, base_url, access_token, course_id, user_id, score, max_score) -> dict``
  * ``pull_courses(*, base_url, access_token) -> list[dict]``

Honest stubs return either an empty success shape (so plumbing tests pass)
or ``{"ok": False, "reason": "scaffold_not_wired"}`` when production
behavior is required. The diagnostics dashboard surfaces a "Scaffold"
pill so operators know not to attempt connection grants yet.

Brightspace API specifics (per Valence Learning Platform docs):
* OAuth2 authorize URL: ``https://auth.brightspace.com/oauth2/auth``
* Token URL: ``https://auth.brightspace.com/core/connect/token``
* Default scopes: ``core:*:* grades:*:read grades:*:write enrollment:*:read``
"""
from __future__ import annotations

import logging
import urllib.parse as _ulib

logger = logging.getLogger(__name__)

# Per Brightspace Valence OAuth2 docs (Apr 2026 snapshot).
DEFAULT_AUTHORIZE_URL = "https://auth.brightspace.com/oauth2/auth"
DEFAULT_TOKEN_URL = "https://auth.brightspace.com/core/connect/token"
DEFAULT_SCOPES = (
    "core:*:*",
    "grades:*:read",
    "grades:*:write",
    "enrollment:*:read",
)

PROVIDER_SLUG = "d2l_brightspace"
PROVIDER_LABEL = "Brightspace (D2L)"


def oauth_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple = DEFAULT_SCOPES,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    """Build the Brightspace OAuth2 authorize URL. Caller must vault
    ``state`` server-side to defend against CSRF."""
    qs = _ulib.urlencode([
        ("response_type", "code"),
        ("client_id", client_id),
        ("redirect_uri", redirect_uri),
        ("state", state),
        ("scope", " ".join(scopes)),
    ])
    sep = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{sep}{qs}"


def refresh_token(*, refresh_token: str, client_id: str, client_secret: str) -> dict:
    """Honest-stub. Returns scaffold_not_wired to make the contract loud."""
    logger.info("d2l_brightspace.refresh_token: scaffold call (not wired)")
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "wave_landed": "v4.00.70"}


def push_grade(*, base_url: str, access_token: str, course_id: str,
               user_id: str, score: float, max_score: float) -> dict:
    """Honest-stub push grade. Real wiring requires Brightspace
    GradeObjects + GradeValues endpoints + ``GET /d2l/api/le/<version>/orgUnit/<id>``
    pre-flight to confirm the orgUnit's grading scheme."""
    logger.info("d2l_brightspace.push_grade: scaffold call (not wired)")
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "course_id": course_id, "user_id": user_id}


def pull_courses(*, base_url: str, access_token: str) -> list[dict]:
    """Honest-stub. Real implementation walks
    ``GET /d2l/api/lp/<version>/enrollments/myenrollments/`` and resolves
    each orgUnit by ID."""
    logger.info("d2l_brightspace.pull_courses: scaffold call (not wired)")
    return []


def is_scaffold() -> bool:
    """Honest declaration — the diagnostics UI checks this to render the
    'Scaffold (coming soon)' pill."""
    return True
