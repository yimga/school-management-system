"""
Policy registry: single entry point for "how should this tenant behave?" (RunMyCampus Execution Map).
Use this module for all policy reads and cache invalidation.
Existing code may still use resolver.get_effective_policy; this is the canonical import.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from apps.policies.resolver import (
    get_effective_policy as _get_effective_policy,
    invalidate_all_tenant_policy_caches as _invalidate_all_tenant_policy_caches,
    invalidate_policy_cache as _invalidate_policy_cache,
)


def get_effective_policy(
    school,
    user=None,
    capability: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single entry point for effective policy: platform_defaults ⊕ country_defaults ⊕ tenant_overrides.
    Returns merged policy dict; use instead of reading School.settings / School.features directly.
    """
    return _get_effective_policy(school, user=user, capability=capability)


def invalidate_policy_cache(school) -> None:
    """Call after updating school.settings or school.features (or blueprint) so policy cache is refreshed."""
    _invalidate_policy_cache(school)


def invalidate_all_tenant_policy_caches() -> None:
    """After the slim tenant site settings row or Phase B snapshots change, bust per-tenant policy cache (if enabled)."""
    _invalidate_all_tenant_policy_caches()


__all__ = [
    "get_effective_policy",
    "invalidate_all_tenant_policy_caches",
    "invalidate_policy_cache",
]
