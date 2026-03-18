"""
Gating: when API Center is enabled, Integration.enabled is the single kill switch.
"""

from apps.platform_runtime.helpers import get_effective_flags_for_school


def is_integration_allowed(integration):
    """
    Return True if the integration may be used.
    - If integration is None -> False.
    - If API Center feature is off -> True (no gating).
    - Else -> integration.enabled (single source of truth).
    """
    if integration is None:
        return False
    flags = get_effective_flags_for_school(getattr(integration, "school", None))
    if not flags.get("enable_api_center", False):
        return True
    return integration.enabled
