"""
Blueprint registry: single entry point for tenant blueprint (RunMyCampus Execution Map).
Use this module for all blueprint reads and apply/preview operations.
Existing code may still use resolver.get_tenant_blueprint or blueprint_services; this is the canonical import.
"""

from __future__ import annotations

from typing import Any, Dict

from apps.policies.blueprint_services import EntitlementRequired
from apps.policies.resolver import get_tenant_blueprint as _get_tenant_blueprint


def get_tenant_blueprint(school) -> Dict[str, Any]:
    """
    Return normalized blueprint for this tenant (school).
    Single source for blueprint data; merges platform ⊕ country ⊕ tenant (via get_effective_policy).
    """
    return _get_tenant_blueprint(school)


# Apply/preview operations — delegate to blueprint_services so one import covers all blueprint operations
def apply_blueprint_pack(school, pack, *, applied_by=None):
    """Apply a BlueprintPack to a school; creates PolicyBundle and sets TenantBlueprint.active_bundle.

    Raises ``EntitlementRequired`` (a ValueError) when the pack is premium commercial
    and the school holds no billing entitlement for it.
    """
    from apps.policies.blueprint_services import apply_blueprint_pack as _apply

    return _apply(school, pack, applied_by=applied_by)


def preview_blueprint_pack(school, pack) -> dict[str, Any]:
    """Preview what would be applied (policy keys, pack summary). No DB write."""
    from apps.policies.blueprint_services import preview_blueprint_pack as _preview

    return _preview(school, pack)


def update_bundle_for_schools(pack, *, school_ids=None, applied_by=None):
    """Re-apply a BlueprintPack to schools that use it (e.g. when pack version increased)."""
    from apps.policies.blueprint_services import update_bundle_for_schools as _update

    return _update(pack, school_ids=school_ids, applied_by=applied_by)


__all__ = [
    "EntitlementRequired",
    "get_tenant_blueprint",
    "apply_blueprint_pack",
    "preview_blueprint_pack",
    "update_bundle_for_schools",
]
