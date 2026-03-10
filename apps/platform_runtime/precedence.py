"""
Metadata precedence chain (plan Workstream I3 / Codex §5).
Effective order: platform default → region → blueprint → policy → plan → tenant → sandbox.
"""
from __future__ import annotations

# Ordered precedence levels; lower index = lower priority (overridden by higher).
PRECEDENCE_ORDER = [
    "platform",
    "region",
    "blueprint",
    "policy_bundle",
    "plan",
    "tenant",
    "sandbox",
]

PRECEDENCE_INDEX = {k: i for i, k in enumerate(PRECEDENCE_ORDER)}


def precedence_rank(scope: str) -> int:
    """Return rank for scope (higher = wins when merging)."""
    return PRECEDENCE_INDEX.get(scope, -1)


def merge_by_precedence(*, values: list[tuple[str, object]]) -> object | None:
    """
    Given [(scope, value), ...], return the value with highest precedence (last in chain).
    """
    if not values:
        return None
    best_scope = max(values, key=lambda x: precedence_rank(x[0]))
    return best_scope[1]
