#!/usr/bin/env python3
"""
Block new app code from importing legacy siteconfig modules for domain-owned
objects that already have bounded-context import surfaces.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_PARTS = {"migrations", "__pycache__", "venv", ".venv", "node_modules", "tests"}
SKIP_PATHS = {
    "apps/brand_experience/models.py",
    "apps/global_registries/models.py",
    "apps/integrations_marketplace/models.py",
    "apps/plans_entitlements/models.py",
    "apps/policies_rules/models.py",
    "apps/runtime_blueprints/models.py",
}
FORBIDDEN_IMPORTS = {
    "apps.siteconfig.models": {
        "BrandProfile": "apps.brand_experience.models",
        "BrandSettings": "apps.brand_experience.models",
        "DesignTemplate": "apps.brand_experience.models",
        "GlobalBrandRegistry": "apps.brand_experience.models",
        "ThemePack": "apps.brand_experience.models",
        "EducationSystemProfile": "apps.global_registries.models",
        "GradingScaleConfig": "apps.global_registries.models",
        "HolidayCalendar": "apps.global_registries.models",
        "Province": "apps.global_registries.models",
        "RegionConfig": "apps.global_registries.models",
        "SystemFeature": "apps.global_registries.models",
        "TenantSystem": "apps.global_registries.models",
        "WeatherLocation": "apps.global_registries.models",
        "Integration": "apps.integrations_marketplace.models",
        "ServiceIntegration": "apps.integrations_marketplace.models",
        "Plan": "apps.plans_entitlements.models",
        "PlanAddon": "apps.plans_entitlements.models",
        "CountryMultiplier": "apps.plans_entitlements.models",
        "FeatureToggleDefinition": "apps.policies_rules.models",
        "FeatureToggleState": "apps.policies_rules.models",
        "TourStep": "apps.policies_rules.models",
    },
    "apps.siteconfig.models_dashboard": {
        "DashboardLayout": "apps.runtime_blueprints.models",
        "DashboardPack": "apps.runtime_blueprints.models",
        "DashboardPackAssignment": "apps.runtime_blueprints.models",
        "DashboardTemplate": "apps.runtime_blueprints.models",
        "DashboardUserPreference": "apps.runtime_blueprints.models",
        "DashboardWidget": "apps.runtime_blueprints.models",
        "SUPER_DASHBOARD_DEFAULT_SECTION_ORDER": "apps.runtime_blueprints.models",
        "SuperAdminDashboardPreference": "apps.runtime_blueprints.models",
        "TenantLayoutAssignment": "apps.runtime_blueprints.models",
        "get_dashboard_widget_metadata": "apps.runtime_blueprints.models",
    },
    "apps.siteconfig.models_workflow": {
        "TenantWorkflow": "apps.runtime_blueprints.models",
        "WorkflowPack": "apps.runtime_blueprints.models",
        "WorkflowPackAssignment": "apps.runtime_blueprints.models",
        "WorkflowTemplate": "apps.runtime_blueprints.models",
    },
}


def _iter_violations(path: Path, rel: str) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text, filename=rel)
    violations: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module
            if not module or module not in FORBIDDEN_IMPORTS:
                continue
            replacements = {
                FORBIDDEN_IMPORTS[module][alias.name]
                for alias in node.names
                if alias.name in FORBIDDEN_IMPORTS[module]
            }
            for replacement in sorted(replacements):
                violations.append((node.lineno, replacement))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module in FORBIDDEN_IMPORTS:
                    replacements = sorted(set(FORBIDDEN_IMPORTS[module].values()))
                    for replacement in replacements:
                        violations.append((node.lineno, replacement))
    return violations


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def main(argv: list[str] | None = None) -> int:
    try:
        base = _resolve_base(parse_args(argv).base)
    except ValueError as exc:
        print(f"lint_siteconfig_legacy_imports: {exc}", file=sys.stderr)
        return 1

    violations: list[tuple[str, int, str]] = []
    for root_name in ("apps", "config"):
        root = base / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            rel = path.relative_to(base).as_posix()
            if rel in SKIP_PATHS or rel.startswith("apps/siteconfig/"):
                continue
            for line_no, replacement in _iter_violations(path, rel):
                violations.append((rel, line_no, replacement))
    if not violations:
        print(
            "lint_siteconfig_legacy_imports: no legacy direct siteconfig domain imports found."
        )
        return 0
    print(
        "lint_siteconfig_legacy_imports: legacy direct siteconfig imports must move to bounded-context surfaces:\n",
        file=sys.stderr,
    )
    for rel, line_no, replacement in violations:
        print(f"  {rel}:{line_no} -> import from {replacement}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
