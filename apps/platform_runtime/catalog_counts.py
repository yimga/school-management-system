"""
§7 Marketplace seed: shared catalog counts for MARKETPLACE_SEED_TARGETS and marketplace UI.

Used by:
- management command platform_inventory (--format json / text)
- marketplace views (governance_console, app_catalog, tenant_app_catalog, blueprint_marketplace)
- apps.platform_runtime.tests.test_marketplace_catalog_minimums (§12 gate)
- scripts/refresh_marketplace_seed_targets.py

Single source of truth for first_party_apps, blueprint_packs, workflow_packs, dashboard_packs,
policy_bundles, and installed_* counts so UI and CLI stay in sync.

Minimums must match docs/MARKETPLACE_SEED_TARGETS.md §1.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from django.db import DatabaseError, OperationalError, ProgrammingError
except ImportError:
    DatabaseError = OperationalError = ProgrammingError = Exception  # type: ignore[misc, assignment]

_EXC = (
    ImportError,
    AttributeError,
    TypeError,
    DatabaseError,
    OperationalError,
    ProgrammingError,
)

# §7 MARKETPLACE_SEED_TARGETS minimums (single source; must match MARKETPLACE_SEED_TARGETS.md §1)
MARKETPLACE_MINIMUMS: dict[str, int] = {
    "first_party_apps": 25,
    "blueprint_packs": 25,
    "workflow_packs": 30,
    "dashboard_packs": 20,
    "policy_bundles": 15,
}


def satisfies_marketplace_minimums(counts: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Return (True, []) if counts meet MARKETPLACE_MINIMUMS; else (False, list of error messages).
    Used by tests and scripts to validate §7 ecosystem seeding.
    """
    errors: list[str] = []
    for key, minimum in MARKETPLACE_MINIMUMS.items():
        value = counts.get(key, 0)
        if not isinstance(value, (int, float)) or value < minimum:
            errors.append(
                f"{key}: got {counts.get(key, 'missing')}, need >= {minimum} (MARKETPLACE_SEED_TARGETS)"
            )
    return (len(errors) == 0, errors)


def get_platform_catalog_counts() -> dict[str, Any]:
    """
    Return catalog and installed counts for platform/marketplace (same shape as platform_inventory).
    Safe to call from views; on DB/import errors returns zeros for affected keys.
    """
    counts: dict[str, Any] = {
        "first_party_apps": 0,
        "blueprint_packs": 0,
        "workflow_packs": 0,
        "dashboard_packs": 0,
        "policy_bundles": 0,
        "installed_blueprint": 0,
        "installed_workflow": 0,
        "installed_dashboard": 0,
        "installed_policy": 0,
        "installed_theme": 0,
    }

    # First-party apps: distinct package_id in PackageVersion
    try:
        from apps.packages.models import PackageVersion

        counts["first_party_apps"] = (
            PackageVersion.objects.values_list("package_id", flat=True)
            .distinct()
            .count()
        )
    except _EXC as e:
        logger.debug("catalog_counts first_party_apps: %s", e)

    # InstalledPackage by type (active only)
    try:
        from apps.packages.models import InstalledPackage
        from django.db.models import Count

        by_type = dict(
            InstalledPackage.objects.filter(is_active=True)
            .values("package_type")
            .annotate(c=Count("id"))
            .values_list("package_type", "c")
        )
        counts["installed_blueprint"] = by_type.get("blueprint", 0)
        counts["installed_workflow"] = by_type.get("workflow", 0)
        counts["installed_dashboard"] = by_type.get("dashboard", 0)
        counts["installed_policy"] = by_type.get("policy", 0)
        counts["installed_theme"] = by_type.get("theme", 0)
    except _EXC as e:
        logger.debug("catalog_counts installed: %s", e)

    # Blueprint / workflow / dashboard packs from runtime_blueprints (catalog)
    try:
        from apps.runtime_blueprints.models import (
            BlueprintPack,
            WorkflowPack,
            DashboardPack,
        )

        counts["blueprint_packs"] = BlueprintPack.objects.count()
        counts["workflow_packs"] = WorkflowPack.objects.count()
        counts["dashboard_packs"] = DashboardPack.objects.count()
    except _EXC as e:
        logger.debug("catalog_counts catalog packs: %s", e)

    # Policy bundles (policies app)
    try:
        from apps.policies.models import PolicyBundle

        counts["policy_bundles"] = PolicyBundle.objects.count()
    except _EXC as e:
        logger.debug("catalog_counts policy_bundles: %s", e)

    return counts
