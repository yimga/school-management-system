"""Ephemeral, cache-backed typing indicators (IM-7).

No DB and no WebSocket (prod is web-only): a single cache key per conversation
holds ``{user_id: [name, expiry_ts]}``. POST marks the caller typing for a few
seconds; GET returns everyone else still within the TTL. Best-effort — a cache
miss just shows nobody typing. Works with any Django cache backend (LocMem in
dev, Redis in prod).

The read-modify-write on the dict is intentionally un-locked: a lost update only
means a transient typer is dropped, and the next keystroke re-marks them. Typing
state is disposable by design.
"""

import time

from django.core.cache import cache
from django.http import JsonResponse

#: How long a single "typing" mark stays live without a refresh.
TYPING_TTL_SECONDS = 6
#: How long the per-conversation cache key itself is retained.
_CACHE_TTL_SECONDS = 30


def typing_cache_key(scope: str, ident) -> str:
    """Stable cache key for a conversation's typing state."""
    return f"rmc_typing_{scope}_{ident}"


def _display_name(user) -> str:
    try:
        full = (user.get_full_name() or "").strip()
    except Exception:  # noqa: BLE001 — name resolution must never raise here
        full = ""
    return full or getattr(user, "username", "") or "Someone"


def mark_typing(key: str, user) -> None:
    """Record ``user`` as typing in the conversation keyed by ``key``."""
    now = time.time()
    data = cache.get(key) or {}
    # Prune anyone whose mark has already expired while we hold the dict.
    data = {uid: v for uid, v in data.items() if v and v[1] > now}
    data[user.id] = [_display_name(user), now + TYPING_TTL_SECONDS]
    cache.set(key, data, _CACHE_TTL_SECONDS)


def current_typers(key: str, exclude_user_id) -> list:
    """Return ``[{id, name}]`` for everyone (but ``exclude_user_id``) still typing."""
    now = time.time()
    data = cache.get(key) or {}
    out = []
    for uid, value in data.items():
        if not value or value[1] <= now or uid == exclude_user_id:
            continue
        out.append({"id": uid, "name": value[0]})
    return out


def typing_response(request, key: str) -> JsonResponse:
    """POST marks the caller typing; GET returns who else is typing."""
    if request.method == "POST":
        mark_typing(key, request.user)
        return JsonResponse({"ok": True})
    return JsonResponse({"typing": current_typers(key, request.user.id)})
