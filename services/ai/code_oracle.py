"""
Live codebase reflection for engine-room support (topology + permission signals).

Facade over ``services.ai.reflection`` so support tooling can ground answers in
real URL patterns without duplicating AST walk logic.
"""

from __future__ import annotations

from typing import Any

from services.ai.context_token_compressor import ContextTokenCompressor
from services.ai.reflection import DynamicSystemInspector, match_path_with_test_hooks

_DEFAULT_COMPRESSOR = ContextTokenCompressor()


def inspect_active_route(path: str) -> dict[str, Any] | None:
    """Return route registry row for *path*, or None."""
    inspector = DynamicSystemInspector()
    row = match_path_with_test_hooks(inspector, path) or inspector.match_path(path)
    if not row:
        return None
    return _DEFAULT_COMPRESSOR.compress_mapping(dict(row))


def build_route_manual_outline(path: str, *, tenant_id: str = "") -> str:
    """
    Dense step outline from topology (no model call). Used when RAG is empty or
    as supplemental context for support_suggest.
    """
    row = inspect_active_route(path)
    if not row:
        return ""
    if tenant_id:
        row = {**row, "tenant_id": tenant_id}
        row = _DEFAULT_COMPRESSOR.compress_mapping(row)
    perms = ", ".join(row.get("required_permissions") or []) or "login_required (inferred)"
    methods = ", ".join(row.get("allowable_methods") or ["GET"])
    name = row.get("name") or "unnamed"
    url_path = row.get("url_path", path)
    blocks = [
        f"**Execution Path**: `{url_path}` (route name: `{name}`)",
        "**Action Steps**:",
        f"1. Confirm you are signed in with the required clearance ({perms}).",
        f"2. Open the screen at the path above (allowed methods: {methods}).",
        "3. Complete the workflow using only controls visible on that screen.",
        "**System Bound**: Permissions and fields come from the live route registry; "
        "if a button is missing, your role may not include this path.",
    ]
    if tenant_id:
        blocks.insert(
            1,
            f"**Tenant scope**: operations apply only to tenant `{tenant_id[:12]}…` "
            "(cross-tenant manuals are blocked).",
        )
    return _DEFAULT_COMPRESSOR.compress_text_blocks(blocks)


def generate_workflow_manual(path: str, *, tenant_id: str = "", school_id: str = "") -> dict[str, Any]:
    """
    Programmatic manual for support/engine-room (no LLM). Row-level scope enforced
    by caller supplying tenant_id; global articles must set tenant_id empty only
    on manager/control-plane routes.
    """
    outline = build_route_manual_outline(path, tenant_id=tenant_id)
    row = inspect_active_route(path)
    return {
        "ok": bool(outline),
        "path": path,
        "tenant_id": tenant_id or None,
        "school_id": school_id or None,
        "route": row,
        "markdown": outline,
    }
