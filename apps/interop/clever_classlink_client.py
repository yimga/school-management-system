"""
Clever API v3.1 and ClassLink Roster Server — client shell for district roster pull.

**Unblocked in code:** OAuth token exchange + roster fetch stubs run when credentials exist.
**Still requires:** Vendor partnership + `CLEVER_CLIENT_ID` / `CLASSLINK_CLIENT_ID` (or per-tenant
ServiceIntegration config) from business development.

Until credentials are provisioned, use OneRoster Bearer + hub (wedge 44 equivalent motion).
"""

from __future__ import annotations

import logging
import urllib.error
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
            import json

            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        logger.warning("Clever API HTTP %s", e.code)
        return {"error": "http_error", "status": e.code}
    except Exception as e:
        logger.exception("Clever fetch failed")
        return {"error": "request_failed", "detail": str(e)[:200]}


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
