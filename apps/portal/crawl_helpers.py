"""
Shared helpers for authenticated HTTP smoke crawls (portal roles, admin changelists).
"""

from __future__ import annotations

_LOGIN_LOCATION_FRAGMENTS = (
    "/login",
    "accounts/login",
    "/authentication/login",
    "password_reset",
)


def portal_smoke_response_ok(response) -> tuple[bool, str]:
    """
    True if the response is not a hard error and not an auth wall redirect.

    Allows 200 and redirects that are not clearly “send to login”.
    """
    code = getattr(response, "status_code", 0)
    if code >= 400:
        return False, f"HTTP {code}"
    if code in (301, 302, 303, 307, 308):
        loc = (response.get("Location") or "").lower()
        for frag in _LOGIN_LOCATION_FRAGMENTS:
            if frag in loc:
                return False, f"redirect to auth: {loc[:200]}"
    return True, ""
