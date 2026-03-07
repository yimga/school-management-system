"""
Policy registry: single entry point for "how should this tenant behave?" (RunMyCampus Execution Map).
Use this module for all policy reads and cache invalidation.
Existing code may still use resolver.get_effective_policy; this is the canonical import.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from apps.policies.resolver import (
    get_effective_policy as _get_effective_policy,
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


__all__ = [
    "get_effective_policy",
    "invalidate_policy_cache",
]
