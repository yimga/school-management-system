"""Offline help contract — sync_engine integration for tenant AI help fallback."""

from __future__ import annotations

from typing import Any


def offline_help_queue_contract() -> dict[str, Any]:
    """Describe what queues when cloud AI is unavailable."""
    return {
        "queue_backend": "apps.api.mobile_api.OfflineSyncQueue",
        "allowed_actions": ["search_help_center", "queue_for_sync"],
        "destructive_requires_confirmation": True,
    }


def enqueue_offline_help_draft(*, school_id: int, user_id: int, draft_key: str) -> dict[str, Any]:
    """Record offline help intent — contract surface for sync_engine (device queue binds at PWA layer)."""
    contract = offline_help_queue_contract()
    return {
        "ok": True,
        "queued": False,
        "contract": contract,
        "draft_key": draft_key[:128],
        "school_id": school_id,
        "user_id": user_id,
    }
