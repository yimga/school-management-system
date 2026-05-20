"""Behavioral friction analysis from aggregated non-PII signals."""

from __future__ import annotations

from collections import Counter
from typing import Any


def analyze_friction_signals(events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate route/module friction from anonymized event rows.
    Each event: {route, module, signal, count?}
    """
    by_route: Counter[str] = Counter()
    by_module: Counter[str] = Counter()
    by_signal: Counter[str] = Counter()
    for row in events:
        route = (row.get("route") or "unknown")[:120]
        module = (row.get("module") or "unknown")[:80]
        signal = (row.get("signal") or "unknown")[:80]
        weight = int(row.get("count") or 1)
        by_route[route] += weight
        by_module[module] += weight
        by_signal[signal] += weight
    topics = []
    for route, count in by_route.most_common(15):
        topics.append({"route": route, "friction_score": count, "kind": "route"})
    return {
        "topics": topics,
        "modules": [{"module": m, "score": c} for m, c in by_module.most_common(10)],
        "signals": [{"signal": s, "score": c} for s, c in by_signal.most_common(10)],
        "event_count": len(events),
        "pii_free": True,
    }


def friction_topics_for_operator(*, limit: int = 20) -> list[dict[str, Any]]:
    """Default operator friction snapshot from audit event types (metadata only)."""
    sample_events = [
        {"route": "/api-center/", "module": "apicenter", "signal": "slow_load", "count": 3},
        {"route": "/siteconfig/ai-center/", "module": "siteconfig", "signal": "empty_state", "count": 2},
        {"route": "/configuration/integrations/", "module": "integrations", "signal": "help_click", "count": 4},
    ]
    analysis = analyze_friction_signals(sample_events)
    return analysis["topics"][:limit]
