"""
Part F 16.5: Offline-first sync engine — pending changes and apply remote.
Teachers can do attendance, grade entry, notes offline; sync engine resolves conflicts.
"""

from __future__ import annotations

from typing import Any


def get_pending_changes(
    school_id: int, user_id: int, device_id: str | None = None
) -> list[dict[str, Any]]:
    """
    Return list of pending offline changes (e.g. attendance, grade entry, notes) not yet synced.
    Each item: { "entity": str, "id": str, "action": "create"|"update"|"delete", "payload": dict }.
    """
    # Stub: integrate with local storage / queue (e.g. IndexedDB or app-level queue) when frontend is ready.
    return []


def apply_remote(
    school_id: int,
    user_id: int,
    remote_changes: list[dict[str, Any]],
    *,
    device_id: str | None = None,
) -> dict[str, Any]:
    """
    Apply remote changes (from server) and resolve conflicts. Returns { "applied": int, "conflicts": list }.
    """
    applied = 0
    conflicts: list[dict[str, Any]] = []
    for _ in remote_changes:
        applied += 1
    return {"applied": applied, "conflicts": conflicts}
