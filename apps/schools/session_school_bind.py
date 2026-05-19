"""
HMAC-backed session school_id binding — ties session campus to authenticated user.

Set on switch-school and when middleware aligns host ↔ session; verified on each
tenant request before handlers run.
"""

from __future__ import annotations

from typing import Any

from django.core import signing

SESSION_SCHOOL_SIG_KEY = "school_bind_sig"
_BIND_SALT = "rmc.session.school-bind.v1"


def sign_session_school_bind(session: Any, *, school_id: str, user_id: Any) -> None:
    """Persist school_id and tamper-evident signature for the active user."""
    sid = str(school_id).strip()
    session["school_id"] = sid
    session[SESSION_SCHOOL_SIG_KEY] = signing.dumps(
        {"sid": sid, "uid": str(user_id)},
        salt=_BIND_SALT,
    )


def verify_session_school_bind(session: Any, user: Any) -> bool:
    """
    Return True when school_id matches signature for user, or school_id is unset.

    Missing signature on an existing school_id is treated as invalid (forces re-bind).
    """
    sid = (session.get("school_id") or "").strip()
    if not sid:
        return True
    sig = session.get(SESSION_SCHOOL_SIG_KEY)
    if not sig:
        return False
    try:
        payload = signing.loads(sig, salt=_BIND_SALT)
    except signing.BadSignature:
        return False
    return payload.get("sid") == sid and payload.get("uid") == str(
        getattr(user, "pk", "")
    )
