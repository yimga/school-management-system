"""Operational health scoring for platform registries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def evaluate_registry_health(
    registries: list[dict[str, Any]],
    *,
    route_inventory: set[str] | None = None,
    now: datetime | None = None,
    stale_after_hours: int = 24,
) -> dict[str, Any]:
    route_inventory = route_inventory or set()
    now = now or datetime.now(timezone.utc)
    rows = []
    for registry in registries:
        generated_at = registry.get("generated_at")
        stale = True
        if isinstance(generated_at, datetime):
            stale = (now - generated_at).total_seconds() > stale_after_hours * 3600
        missing_owner = not bool(registry.get("owner"))
        missing_proof = not bool(registry.get("proof"))
        missing_tests = not bool(registry.get("test") or registry.get("tests"))
        route = str(registry.get("route") or "")
        missing_route = bool(route_inventory) and route not in route_inventory
        status = str(registry.get("status") or "")
        external_blocker = status == "external_required"
        severity = "ok"
        if missing_owner or missing_proof or missing_route:
            severity = "high"
        elif missing_tests or stale:
            severity = "medium"
        elif external_blocker:
            # Honest external posture — tracked in SOT, not a repo registry defect.
            severity = "ok"
        rows.append(
            {
                "registry_name": registry.get("name", ""),
                "owner": registry.get("owner", ""),
                "scope": registry.get("scope", ""),
                "route": route,
                "last_generated": generated_at.isoformat() if isinstance(generated_at, datetime) else "",
                "stale": stale,
                "drift_detected": missing_route,
                "missing_tests": missing_tests,
                "missing_proof": missing_proof,
                "missing_owner": missing_owner,
                "external_blocker": external_blocker,
                "severity": severity,
                "primary_action": "Close registry proof gaps." if severity != "ok" else "Monitor",
            }
        )
    return {
        "ok": all(row["severity"] == "ok" for row in rows),
        "rows": rows,
        "high_count": sum(1 for row in rows if row["severity"] == "high"),
        "medium_count": sum(1 for row in rows if row["severity"] == "medium"),
    }
