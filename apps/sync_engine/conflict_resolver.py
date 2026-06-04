"""Conflict-resolution strategies for offline sync replay.

``apply_remote`` (apps/sync_engine/services.py) detects duplicate-key conflicts
but intentionally does not decide what to do — that is a per-entity policy
choice. This module supplies the canonical strategies so the caller can
``resolve_conflicts(conflicts, strategy=...)`` and get a deterministic outcome.

Strategies:

- ``last_write_wins``   — keep the most recent change (highest ``timestamp``)
- ``server_authoritative`` — drop the remote change; server-side row stays
- ``manual_review``     — leave the conflict for an operator to triage; never
                          auto-applies. Used when correctness matters more
                          than throughput (e.g. financial entries).

Per-entity defaults are configurable via ``DEFAULT_STRATEGY_PER_ENTITY``.
"""

from __future__ import annotations

from typing import Any

from datetime import datetime, timezone


class ResolutionStrategy:
    LAST_WRITE_WINS = "last_write_wins"
    SERVER_AUTHORITATIVE = "server_authoritative"
    MANUAL_REVIEW = "manual_review"


# Per-entity default strategy. Anything not listed falls back to MANUAL_REVIEW
# (safe-by-default — operator must opt into auto-resolution per entity type).
DEFAULT_STRATEGY_PER_ENTITY: dict[str, str] = {
    "attendance_record": ResolutionStrategy.LAST_WRITE_WINS,
    "student_note": ResolutionStrategy.LAST_WRITE_WINS,
    "lesson_plan": ResolutionStrategy.LAST_WRITE_WINS,
    "grade_entry": ResolutionStrategy.MANUAL_REVIEW,  # money-adjacent, never auto
    "payment_proof_upload": ResolutionStrategy.MANUAL_REVIEW,
    "invoice_line": ResolutionStrategy.MANUAL_REVIEW,
    "user_profile": ResolutionStrategy.SERVER_AUTHORITATIVE,
    "permission_grant": ResolutionStrategy.SERVER_AUTHORITATIVE,
}


def _parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    # Try common ISO 8601 forms; never raise on unparseable strings.
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def resolve_one(
    conflict: dict[str, Any],
    *,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Decide what to do with a single conflict.

    Returns a dict shaped:
      ``{"action": "keep_remote"|"keep_server"|"manual_review", "reason": "..."}``
    """
    entity = str(conflict.get("entity") or "").strip()
    chosen = (
        strategy
        or DEFAULT_STRATEGY_PER_ENTITY.get(entity, ResolutionStrategy.MANUAL_REVIEW)
    )

    if chosen == ResolutionStrategy.MANUAL_REVIEW:
        return {"action": "manual_review", "reason": f"entity={entity!r} requires operator triage"}

    if chosen == ResolutionStrategy.SERVER_AUTHORITATIVE:
        return {"action": "keep_server", "reason": "server_authoritative policy for entity"}

    if chosen == ResolutionStrategy.LAST_WRITE_WINS:
        remote_ts = _parse_ts(conflict.get("remote_timestamp") or conflict.get("timestamp"))
        server_ts = _parse_ts(conflict.get("server_timestamp"))
        if remote_ts is None or server_ts is None:
            # Without timestamps we cannot pick — fall through to manual review.
            return {
                "action": "manual_review",
                "reason": "last_write_wins requires remote_timestamp + server_timestamp",
            }
        if remote_ts > server_ts:
            return {"action": "keep_remote", "reason": "remote is newer"}
        if server_ts > remote_ts:
            return {"action": "keep_server", "reason": "server is newer"}
        return {"action": "keep_server", "reason": "tie: prefer server"}

    return {"action": "manual_review", "reason": f"unknown strategy {chosen!r}"}


def resolve_conflicts(
    conflicts: list[dict[str, Any]],
    *,
    strategy: str | None = None,
    per_entity_override: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve a batch of conflicts and return a list of decisions.

    ``per_entity_override`` lets the caller supply a partial entity→strategy map
    that wins over ``DEFAULT_STRATEGY_PER_ENTITY``. ``strategy`` (when set) is
    used for all conflicts whose entity has no override.
    """
    overrides = per_entity_override or {}
    decisions: list[dict[str, Any]] = []
    for c in conflicts:
        entity = str(c.get("entity") or "").strip()
        s = overrides.get(entity, strategy)
        decisions.append({"conflict": c, "decision": resolve_one(c, strategy=s)})
    return decisions


__all__ = [
    "ResolutionStrategy",
    "DEFAULT_STRATEGY_PER_ENTITY",
    "resolve_one",
    "resolve_conflicts",
]
