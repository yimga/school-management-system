"""Classification + ticket helpers for North Star self-heal (importable by tests)."""

from __future__ import annotations

import re
from pathlib import Path


def categorize_failure(script_label: str, stderr: str, stdout: str) -> str:
    blob = f"{stderr}\n{stdout}".lower()
    combined = f"{script_label}:{blob}"
    if "inventory" in blob or "platform_inventory" in blob:
        return "inventory_drift"
    if "i18n" in blob or "catalog" in blob:
        return "i18n_drift"
    if "doc plan" in blob or "density" in blob:
        return "doc_density_drift"
    if "shell" in blob or "surface_inventory" in blob:
        return "shell_marker_missing"
    if "admin gravity" in combined or "admin_fallback" in blob:
        return "admin_fallback_ordering"
    if "tenant_isolation" in combined:
        return "tenant_isolation_gap"
    if "permission" in blob:
        return "permission_gap"
    if "security_surface" in combined:
        return "security_surface_gap"
    if "post_surface" in blob or "post_handler" in blob:
        return "post_surface_gap"
    if "regional_ui" in blob or "audit_regional_ui_surface" in combined:
        return "regional_ui_gap"
    if "test_module_contract" in combined:
        return "test_contract_gap"
    if "fail" in blob and ("test" in blob or "error" in blob):
        return "test_failure"
    return "unknown"


_SAFE_SLUG = re.compile(r"[^a-zA-Z0-9_-]+")


def ticket_slug(category: str, excerpt: str) -> str:
    frag = excerpt.strip().replace("\n", " ")[:48]
    frag = _SAFE_SLUG.sub("-", frag).strip("-").lower()
    return frag or category


def write_ticket(
    tickets_dir: Path,
    *,
    category: str,
    command: str,
    excerpt: str,
    cause: str,
    action: str,
    affected_files: list[str],
    risk: str,
    test_command: str,
    timestamp: str,
) -> Path:
    tickets_dir.mkdir(parents=True, exist_ok=True)
    slug = ticket_slug(category, excerpt)
    fname = f"{timestamp}_{category}_{slug}.md"
    path = tickets_dir / fname
    lines = [
        "# Self-heal repair ticket",
        "",
        f"- **category:** {category}",
        f"- **detected command:** `{command}`",
        "",
        "## Excerpt",
        "",
        "```text",
        excerpt.strip()[-8000:] if excerpt.strip() else "(empty)",
        "```",
        "",
        "## Suspected cause",
        "",
        cause,
        "",
        "## Required action",
        "",
        action,
        "",
        "## Affected files / areas",
        "",
        "\n".join(f"- `{a}`" for a in affected_files) or "- (unknown)",
        "",
        f"## Risk: **{risk}**",
        "",
        "## Recommended test",
        "",
        f"`{test_command}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
