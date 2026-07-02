"""Canonical, policy-governed conflict resolution for offline sync replay."""

from __future__ import annotations

from typing import Any

from apps.sync_engine.crdt_wire_protocol import HLC
from apps.sync_engine.policy_registry import (
    MergeStrategy,
    POLICIES,
    POLICY_VERSION,
    get_policy,
    normalize_entity,
)


class ResolutionStrategy:
    # Compatibility name retained for existing callers. It now means causal
    # logical-clock ordering, never a raw wall-clock race.
    LAST_WRITE_WINS = MergeStrategy.CAUSAL_LWW
    CAUSAL_LWW = MergeStrategy.CAUSAL_LWW
    SERVER_AUTHORITATIVE = MergeStrategy.SERVER_AUTHORITATIVE
    MANUAL_REVIEW = MergeStrategy.MANUAL_REVIEW
    FIELD_MERGE = MergeStrategy.FIELD_MERGE
    APPEND_ONLY = MergeStrategy.APPEND_ONLY
    ONLINE_REQUIRED = MergeStrategy.ONLINE_REQUIRED


DEFAULT_STRATEGY_PER_ENTITY: dict[str, str] = {
    entity: policy.strategy for entity, policy in POLICIES.items()
}


def _parse_causal_rank(value: Any) -> tuple[int, int, str] | None:
    if isinstance(value, HLC):
        return (value.physical_ms, value.logical, value.actor_id)
    if isinstance(value, str):
        try:
            parsed = HLC.from_wire(value)
        except ValueError:
            return None
        return (parsed.physical_ms, parsed.logical, parsed.actor_id)
    if isinstance(value, dict):
        try:
            logical = int(value.get("lamport", value.get("logical")))
        except (TypeError, ValueError):
            return None
        replica = str(
            value.get("replica_id") or value.get("actor_id") or ""
        ).strip()
        if logical < 0 or not replica:
            return None
        return (0, logical, replica)
    return None


def _causal_decision(conflict: dict[str, Any]) -> dict[str, Any]:
    remote_rank = _parse_causal_rank(
        conflict.get("remote_clock")
        or conflict.get("remote_hlc")
        or conflict.get("remote_revision")
    )
    server_rank = _parse_causal_rank(
        conflict.get("server_clock")
        or conflict.get("server_hlc")
        or conflict.get("server_revision")
    )
    if remote_rank is None or server_rank is None:
        return {
            "action": "manual_review",
            "reason": "causal_lww requires remote_clock and server_clock",
        }
    if remote_rank > server_rank:
        return {"action": "keep_remote", "reason": "remote causal rank is newer"}
    if server_rank > remote_rank:
        return {"action": "keep_server", "reason": "server causal rank is newer"}
    return {"action": "keep_server", "reason": "causal rank tie: prefer server"}


def resolve_one(
    conflict: dict[str, Any],
    *,
    strategy: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic resolution decision with policy evidence."""
    entity = normalize_entity(conflict.get("entity") or "")
    policy = get_policy(entity)
    override_blocked = bool(
        strategy and policy.protected and strategy != policy.strategy
    )
    chosen = policy.strategy if override_blocked else (strategy or policy.strategy)

    if chosen == MergeStrategy.MANUAL_REVIEW:
        decision = {
            "action": "manual_review",
            "reason": f"entity={entity!r} requires operator triage",
        }
    elif chosen == MergeStrategy.SERVER_AUTHORITATIVE:
        decision = {
            "action": "keep_server",
            "reason": "server_authoritative policy for entity",
        }
    elif chosen == MergeStrategy.CAUSAL_LWW:
        decision = _causal_decision(conflict)
    elif chosen == MergeStrategy.APPEND_ONLY:
        decision = {
            "action": "manual_review",
            "reason": "append-only entities require unique operation IDs; overwrite rejected",
        }
    elif chosen == MergeStrategy.FIELD_MERGE:
        decision = {
            "action": "manual_review",
            "reason": "field merge requires a typed domain handler",
        }
    elif chosen == MergeStrategy.ONLINE_REQUIRED:
        decision = {
            "action": "reject_offline",
            "reason": (
                "entity requires a live online transaction; an offline replica "
                "must never queue or replay it"
            ),
        }
    else:
        decision = {
            "action": "manual_review",
            "reason": f"unknown strategy {chosen!r}",
        }

    decision.update(
        {
            "entity": entity,
            "strategy": chosen,
            "policy_version": POLICY_VERSION,
            "protected_policy": policy.protected,
            "override_blocked": override_blocked,
        }
    )
    return decision


def resolve_conflicts(
    conflicts: list[dict[str, Any]],
    *,
    strategy: str | None = None,
    per_entity_override: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve conflicts while refusing overrides of protected policies."""
    overrides = {
        normalize_entity(entity): value
        for entity, value in (per_entity_override or {}).items()
    }
    decisions: list[dict[str, Any]] = []
    for conflict in conflicts:
        entity = normalize_entity(conflict.get("entity") or "")
        selected = overrides.get(entity, strategy)
        decisions.append(
            {
                "conflict": conflict,
                "decision": resolve_one(conflict, strategy=selected),
            }
        )
    return decisions


__all__ = [
    "DEFAULT_STRATEGY_PER_ENTITY",
    "ResolutionStrategy",
    "resolve_conflicts",
    "resolve_one",
]
