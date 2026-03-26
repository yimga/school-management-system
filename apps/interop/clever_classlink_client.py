"""
Clever API v3.1 and ClassLink Roster Server — client shell for district roster pull.

**Unblocked in code:** OAuth token exchange + roster fetch stubs run when credentials exist.
**Still requires:** Vendor partnership + `CLEVER_CLIENT_ID` / `CLASSLINK_CLIENT_ID` (or per-tenant
ServiceIntegration config) from business development.

When district tokens are absent, responses are structured errors (no network). With valid
tokens, performs real HTTPS calls to vendor endpoints (Clever v3.1, ClassLink OneRoster host).
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

CLEVER_API = "https://api.clever.com/v3.1"
CLASSLINK_API = (
    "https://oneroster.classlink.io/v1p1"  # district-specific host often required
)


def clever_list_users(bearer_token: str, *, limit: int = 100) -> dict[str, Any]:
    """GET /v3.1/users — requires district bearer from Clever Secure Sync / partnership."""
    if not bearer_token or len(bearer_token) < 8:
        return {
            "error": "missing_token",
            "detail": "Set Clever bearer after partnership onboarding.",
        }
    req = urllib.request.Request(
        f"{CLEVER_API}/users?limit={limit}",
        headers={"Authorization": f"Bearer {bearer_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.warning("Clever API HTTP %s", e.code)
        return {"error": "http_error", "status": e.code}
    except Exception as e:
        logger.exception("Clever fetch failed")
        return {"error": "request_failed", "detail": str(e)[:200]}


def clever_list_schools(bearer_token: str, *, limit: int = 50) -> dict[str, Any]:
    """GET /v3.1/schools — district-scoped when bearer is a district token."""
    if not bearer_token or len(bearer_token) < 8:
        return {"error": "missing_token"}
    req = urllib.request.Request(
        f"{CLEVER_API}/schools?limit={limit}",
        headers={"Authorization": f"Bearer {bearer_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": "http_error", "status": e.code}
    except Exception as e:
        return {"error": "request_failed", "detail": str(e)[:200]}


def clever_list_sections(bearer_token: str, *, limit: int = 50) -> dict[str, Any]:
    """GET /v3.1/sections — class/section roster grouping."""
    if not bearer_token or len(bearer_token) < 8:
        return {"error": "missing_token"}
    req = urllib.request.Request(
        f"{CLEVER_API}/sections?limit={limit}",
        headers={"Authorization": f"Bearer {bearer_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": "http_error", "status": e.code}
    except Exception as e:
        return {"error": "request_failed", "detail": str(e)[:200]}


CLEVER_TOKEN_URL = "https://clever.com/oauth/tokens"


def clever_oauth_token_exchange(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """
    Exchange authorization code for bearer access token (Clever OAuth 2.0).
    Requires valid app credentials from Clever developer / district onboarding.
    """
    if not all((client_id, client_secret, code, redirect_uri)):
        return {"error": "missing_fields"}
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
    ).encode()
    req = urllib.request.Request(
        CLEVER_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": "Basic "
            + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode(),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()[:500]
        except OSError:
            detail = str(e.code)
        return {"error": "http_error", "status": e.code, "detail": detail}
    except Exception as e:
        return {"error": "request_failed", "detail": str(e)[:200]}


def classlink_list_courses(bearer_token: str, district_path: str = "") -> dict[str, Any]:
    """GET .../courses?limit=5 — OneRoster courses on ClassLink host."""
    base = (district_path or CLASSLINK_API).rstrip("/")
    if not bearer_token:
        return {"error": "missing_token"}
    req = urllib.request.Request(
        f"{base}/courses?limit=5",
        headers={"Authorization": f"Bearer {bearer_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": "http_error", "status": e.code}
    except Exception as e:
        return {"error": str(e)[:120]}


def classlink_roster_ping(bearer_token: str, district_path: str = "") -> dict[str, Any]:
    """
    OneRoster-shaped ping; ClassLink uses per-district base URL — pass full base if known.
    """
    base = (district_path or CLASSLINK_API).rstrip("/")
    if not bearer_token:
        return {"error": "missing_token"}
    req = urllib.request.Request(
        f"{base}/users?limit=1",
        headers={"Authorization": f"Bearer {bearer_token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"error": "http_error", "status": e.code}
    except Exception as e:
        return {"error": str(e)[:120]}
