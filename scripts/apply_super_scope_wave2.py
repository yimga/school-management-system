#!/usr/bin/env python3
"""Add @require_platform_scope to remaining /super/ view modules (wave 2)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHOOLS = ROOT / "apps" / "schools"

SCOPE_IMPORT = """from apps.platform_runtime.operator_identity import (
    {imports}
    require_platform_scope,
)
"""

# module -> list of (function_name, scope_constant) or ("*", scope) for all defs
WAVE2: dict[str, list[tuple[str, str]]] = {
    "super_views_exports.py": [
        ("*", "PLATFORM_SCOPE_AUDIT_EXPORT"),
    ],
    "super_views_catalog.py": [
        ("*", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_ai.py": [
        ("*", "PLATFORM_SCOPE_SECURITY_READ"),
    ],
    "super_views_founder_dashboard.py": [
        ("*", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_command_center_views.py": [
        ("*", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_dashboard_surfaces.py": [
        ("*", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_phase_b.py": [
        ("*", "PLATFORM_SCOPE_SECURITY_READ"),
    ],
    "super_views_create_school_wizard.py": [
        ("*", "PLATFORM_SCOPE_PROVISION"),
    ],
    "super_views_geo_api.py": [
        ("*", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_support.py": [
        ("super_support_dashboard", "PLATFORM_SCOPE_TEAM_READ"),
        ("support_queue_fragment", "PLATFORM_SCOPE_TEAM_READ"),
        ("support_assign_ticket", "PLATFORM_SCOPE_TEAM_MANAGE"),
        ("super_support_ticket_detail", "PLATFORM_SCOPE_TEAM_READ"),
        ("super_support_csat_dashboard", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_config_crud.py": [
        ("*", "PLATFORM_SCOPE_SECURITY_WRITE"),
    ],
    "super_views_wedge.py": [
        ("*", "PLATFORM_SCOPE_TENANT_READ"),
    ],
    "super_views_tenant_offboarding.py": [
        ("api_school_offboarding", "PLATFORM_SCOPE_FLEET"),
        ("api_school_offboarding_export", "PLATFORM_SCOPE_AUDIT_EXPORT"),
        ("api_school_offboarding_deactivate", "PLATFORM_SCOPE_FLEET"),
        ("api_school_offboarding_hold", "PLATFORM_SCOPE_FLEET"),
        ("api_school_offboarding_purge", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("api_school_offboarding_dual_approve", "PLATFORM_SCOPE_SECURITY_WRITE"),
    ],
    "super_views_school_api.py": [
        ("api_school_timeline", "PLATFORM_SCOPE_TENANT_READ"),
        ("school_lifecycle_action", "PLATFORM_SCOPE_FLEET"),
        ("api_school_policy_bundles", "PLATFORM_SCOPE_SECURITY_READ"),
        ("api_school_policy_bundle_activate", "PLATFORM_SCOPE_SECURITY_WRITE"),
    ],
    "super_views_offboarding_queue.py": [
        ("api_super_run_scheduled_purges", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("api_school_offboarding_schedule", "PLATFORM_SCOPE_FLEET"),
        ("api_school_offboarding_export_download", "PLATFORM_SCOPE_AUDIT_EXPORT"),
    ],
    "super_views_config.py": [
        ("super_admin_bridge", "PLATFORM_SCOPE_SECURITY_READ"),
        ("super_admin_bridge_legacy_path_redirect", "PLATFORM_SCOPE_SECURITY_READ"),
        ("super_platform_operator_hub", "PLATFORM_SCOPE_TEAM_READ"),
        ("super_operator_policy", "PLATFORM_SCOPE_SECURITY_READ"),
        ("super_site_settings_list", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_site_settings_edit", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_regions_list", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_grading_list", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_plans_list", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_country_multipliers_list", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_feature_toggles_list", "PLATFORM_SCOPE_SECURITY_WRITE"),
        ("super_backlog_unlock_center", "PLATFORM_SCOPE_FLEET"),
    ],
}


def _ensure_imports(text: str, scopes: set[str]) -> str:
    if "require_platform_scope" in text:
        needed = scopes - set(re.findall(r"PLATFORM_SCOPE_\w+", text))
        if not needed:
            return text
    block = SCOPE_IMPORT.format(imports=",\n    ".join(sorted(scopes)) + ",")
    if "from apps.platform_runtime.operator_identity import" in text:
        return text
    lines = text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from ") or line.startswith("import "):
            insert_at = i + 1
        elif insert_at and line.strip() and not line.startswith("#"):
            break
    lines.insert(insert_at, block.rstrip())
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")


def _decorate_function(text: str, func_name: str, scope: str) -> str:
    if f"@require_platform_scope({scope})" in text and f"def {func_name}(" in text:
        # already decorated near this function?
        pattern = re.compile(
            rf"@require_platform_scope\({re.escape(scope)}\)\s*\n(?:@\w+.*\n)*def {re.escape(func_name)}\(",
            re.MULTILINE,
        )
        if pattern.search(text):
            return text
    pattern = re.compile(
        rf"(^def {re.escape(func_name)}\()",
        re.MULTILINE,
    )

    def repl(m: re.Match[str]) -> str:
        start = m.start()
        prefix = text[max(0, start - 500) : start]
        if "@require_platform_scope(" in prefix:
            return m.group(0)
        return f"@require_platform_scope({scope})\n{m.group(0)}"

    return pattern.sub(repl, text, count=1)


def main() -> int:
    changed_files = 0
    for module, rules in WAVE2.items():
        path = SCHOOLS / module
        if not path.is_file():
            print(f"SKIP missing {module}")
            continue
        text = path.read_text(encoding="utf-8")
        scopes = {scope for _, scope in rules}
        new_text = _ensure_imports(text, scopes)
        star_scope = next((s for n, s in rules if n == "*"), None)
        if star_scope:
            for m in re.finditer(r"^def (\w+)\(", new_text, re.MULTILINE):
                fname = m.group(1)
                if fname.startswith("_"):
                    continue
                new_text = _decorate_function(new_text, fname, star_scope)
        else:
            for fname, scope in rules:
                if fname == "*":
                    continue
                new_text = _decorate_function(new_text, fname, scope)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed_files += 1
            print(f"UPDATED {module}")
    print(f"apply_super_scope_wave2: {changed_files} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
