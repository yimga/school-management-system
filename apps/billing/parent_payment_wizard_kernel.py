"""Parent payment setup wizard → non-secret payment preference ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_parent_payment_step(
    *,
    school: Any | None,
    actor_user_id: int | None,
    step_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if school is None or not actor_user_id:
        return {"ok": False}

    settings = dict(getattr(school, "settings", None) or {})
    root = dict(settings.get("parent_payment_setup") or {})
    users = dict(root.get("users") or {})
    user_row = dict(users.get(str(actor_user_id)) or {})
    user_row[step_key] = {**dict(payload or {}), "updated_at": _utc_now()}
    users[str(actor_user_id)] = user_row
    root["users"] = users
    root["updated_at"] = _utc_now()
    settings["parent_payment_setup"] = root
    school.settings = settings
    school.save(update_fields=["settings"])
    return {"ok": True, "step_key": step_key}
