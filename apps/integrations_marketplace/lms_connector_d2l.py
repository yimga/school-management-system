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

# v4.00.72 — OAuth state mint TimestampSigner salt + TTL.
OAUTH_STATE_SALT = "rmc.lms.d2l_brightspace.oauth_state.v4.00.72"
OAUTH_STATE_TTL_SECONDS = 600  # 10 min


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


def mint_oauth_state(*, tenant_slug: str, user_pk: str | int,
                      redirect_path: str = "/") -> str:
    """v4.00.72 — Mint a CSRF-safe OAuth state signed w/ TimestampSigner.
    Payload format: ``"<tenant_slug>:<user_pk>:<redirect_path>"``.
    Open-redirect defense: redirect_path must start with "/" not "//".
    """
    from django.core.signing import TimestampSigner
    signer = TimestampSigner(salt=OAUTH_STATE_SALT)
    safe_redirect = redirect_path if redirect_path.startswith("/") and not redirect_path.startswith("//") else "/"
    payload = f"{tenant_slug}:{user_pk}:{safe_redirect}"
    return signer.sign(payload)


def read_oauth_state(raw: str):
    """v4.00.72 — Return ``(parsed_dict_or_None, reason)``. 5-state taxonomy."""
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
    """Honest-stub. Returns scaffold_not_wired to make the contract loud."""
    logger.info("d2l_brightspace.refresh_token: scaffold call (not wired)")
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "wave_landed": "v4.00.70"}


def push_grade(*, base_url: str, access_token: str, course_id: str,
               user_id: str, score: float, max_score: float,
               grade_object_id: str = "", api_version: str = "1.66",
               comment: str = "") -> dict:
    """v4.00.76 — Honest-stub. Real wiring requires Brightspace GradeObjects
    + GradeValues endpoints + a pre-flight ``GET /d2l/api/le/<version>/orgUnit/<id>``
    to confirm the orgUnit's grading scheme.

    Returns the intended request shape under ``would_send`` so caller code
    can unit-test payload assembly without hitting the network. Local
    validation mirrors v4.00.75 Schoology push_grade so callers can rely
    on identical error reason taxonomy across providers.
    """
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

    # Brightspace API: PUT /d2l/api/le/<ver>/<orgUnitId>/grades/<gradeObjId>/values/<userId>
    endpoint = (
        f"{base_url.rstrip('/')}/d2l/api/le/{api_version}/{course_id}"
        f"/grades/{grade_object_id or 'unknown'}/values/{user_id}"
    )
    payload_shape = {
        "endpoint": endpoint,
        "method": "PUT",
        "body": {
            "GradeObjectType": 1,  # 1 = Numeric grade per Brightspace docs
            "PointsNumerator": s,
            "PointsDenominator": m,
            "Comments": {"Content": comment, "Type": "Text"} if comment else None,
        },
    }
    logger.info("d2l_brightspace.push_grade: scaffold call (would send %s)", endpoint)
    return {"ok": False, "reason": "scaffold_not_wired",
            "provider": PROVIDER_SLUG, "course_id": course_id, "user_id": user_id,
            "would_send": payload_shape}


def pull_courses(*, base_url: str, access_token: str) -> list[dict]:
    """Honest-stub. Real implementation walks
    ``GET /d2l/api/lp/<version>/enrollments/myenrollments/`` and resolves
    each orgUnit by ID."""
    logger.info("d2l_brightspace.pull_courses: scaffold call (not wired)")
    return []


def is_scaffold() -> bool:
    # v4.00.84 — D2L Brightspace promoted to OAUTH_READY in
    # lms_supported_providers. Kept returning False so callers checking the
    # adapter directly see the current maturity. The honest-stub push_grade
    # above remains for dry-run consumers; live outbound is gated by
    # ``push_grade_live`` + env flag.
    return False


# ---------------------------------------------------------------------------
# v4.00.84 — Live OAuth code-exchange + push_grade_live (gated behind env flag).
# ---------------------------------------------------------------------------
import os
import logging

logger = logging.getLogger(__name__)

LIVE_OUTBOUND_ENV = "RMC_D2L_OAUTH_LIVE_OUTBOUND"

# D2L Brightspace Valence API version anchor. Bump as Brightspace publishes
# new minor versions of the LE (Learning Environment) product API.
_DEFAULT_API_VERSION = "1.46"


def _live_outbound_enabled() -> bool:
    return os.environ.get(LIVE_OUTBOUND_ENV, "") in ("1", "true", "yes", "on")


def exchange_authorization_code_for_token(*, code: str, client_id: str, client_secret: str, redirect_uri: str, token_url: str = DEFAULT_TOKEN_URL, timeout: int = 15) -> dict:
    """Exchange an OAuth authorization code for an access token against
    Brightspace's ``/core/connect/token`` endpoint.

    When LIVE_OUTBOUND_ENV is unset (default), returns a dry-run dict that
    looks like a Brightspace success response — useful for testing the
    plumbing without hitting prod.

    On real outbound: returns the upstream JSON OR a structured error dict
    if the upstream returned non-2xx / network error. NEVER raises.

    NEVER logs client_secret / access_token / refresh_token (PII guard).
    """
    if not _live_outbound_enabled():
        return {
            "access_token": "dry-run-access-token",
            "refresh_token": "dry-run-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": " ".join(DEFAULT_SCOPES) if DEFAULT_SCOPES else "",
            "dry_run": True,
            "reason": "live_outbound_disabled_env_unset",
        }
    try:
        import requests
    except ImportError:
        return {"dry_run": False, "ok": False, "reason": "requests_lib_missing"}

    try:
        resp = requests.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("d2l_brightspace token exchange network error: %s", type(exc).__name__)
        return {"dry_run": False, "ok": False, "reason": "network_error", "exc_type": type(exc).__name__}

    if not (200 <= resp.status_code < 300):
        logger.warning("d2l_brightspace token exchange http_%s", resp.status_code)
        return {"dry_run": False, "ok": False, "reason": "http_error", "http_status": resp.status_code}

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return {"dry_run": False, "ok": False, "reason": "json_parse_error", "http_status": resp.status_code}

    body["dry_run"] = False
    body["ok"] = True
    return body


def push_grade_live(*, access_token: str, org_unit_id: str, grade_object_id: str, user_id: str, score: float, max_score: float, comment: str = "", api_base: str = "https://your-tenant.brightspace.com", api_version: str = _DEFAULT_API_VERSION, timeout: int = 15) -> dict:
    """REAL outbound push_grade against D2L Brightspace's
    ``PUT /d2l/api/le/<ver>/<orgUnit>/grades/<gradeObj>/values/<user>``
    endpoint. Gated behind LIVE_OUTBOUND_ENV. Returns upstream JSON on
    success, structured error dict on failure. NEVER raises."""
    target = (
        f"{api_base.rstrip('/')}/d2l/api/le/{api_version}/{org_unit_id}"
        f"/grades/{grade_object_id}/values/{user_id}"
    )
    if not _live_outbound_enabled():
        return {
            "ok": False,
            "dry_run": True,
            "reason": "live_outbound_disabled_env_unset",
            "would_target": target,
        }
    try:
        import requests
    except ImportError:
        return {"ok": False, "dry_run": False, "reason": "requests_lib_missing"}

    payload = {
        "PointsNumerator": float(score),
        "Comments": {"Content": comment[:1000], "Type": "Text"},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    try:
        resp = requests.put(
            target,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "dry_run": False, "reason": "network_error", "exc_type": type(exc).__name__}

    if not (200 <= resp.status_code < 300):
        return {"ok": False, "dry_run": False, "reason": "http_error", "http_status": resp.status_code}

    try:
        return {"ok": True, "dry_run": False, "http_status": resp.status_code, "upstream": resp.json()}
    except Exception:  # noqa: BLE001
        return {"ok": True, "dry_run": False, "http_status": resp.status_code}
