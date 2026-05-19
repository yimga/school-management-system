"""
Live codebase reflection for engine-room support (topology + permission signals).

Facade over ``services.ai.reflection`` so support tooling can ground answers in
real URL patterns without duplicating AST walk logic.
"""

from __future__ import annotations

from typing import Any

from services.ai.reflection import DynamicSystemInspector, match_path_with_test_hooks


def inspect_active_route(path: str) -> dict[str, Any] | None:
    """Return route registry row for *path*, or None."""
    inspector = DynamicSystemInspector()
    return match_path_with_test_hooks(inspector, path) or inspector.match_path(path)


def build_route_manual_outline(path: str) -> str:
    """
    Dense step outline from topology (no model call). Used when RAG is empty or
    as supplemental context for support_suggest.
    """
    row = inspect_active_route(path)
    if not row:
        return ""
    perms = ", ".join(row.get("required_permissions") or []) or "login_required (inferred)"
    methods = ", ".join(row.get("allowable_methods") or ["GET"])
    name = row.get("name") or "unnamed"
    return (
        f"**Execution Path**: `{row.get('url_path', path)}` (route name: `{name}`)\n"
        f"**Action Steps**:\n"
        f"1. Confirm you are signed in with the required clearance ({perms}).\n"
        f"2. Open the screen at the path above (allowed methods: {methods}).\n"
        f"3. Complete the workflow using only controls visible on that screen.\n"
        f"**System Bound**: Permissions and fields come from the live route registry; "
        f"if a button is missing, your role may not include this path."
    )
