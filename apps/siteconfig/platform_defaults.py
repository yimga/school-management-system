"""
Platform defaults for site config (B2 — SiteSettings holds platform defaults only).
Canonical default values used when no tenant/school override exists.
"""

from __future__ import annotations

# Keys and defaults used by get_effective_* and runtime; avoid reading SiteSettings in tenant paths.
PLATFORM_DEFAULT_BACKEND_FEATURE_FLAGS: dict[str, object] = {
    "enable_api_schema_ui": True,
    "allowed_roles_api_schema": [],
    "require_guardian_finance_opt_in": False,
}
PLATFORM_DEFAULT_REGION_CODE = "GLOBAL"
PLATFORM_DEFAULT_CURRENCY = "USD"
PLATFORM_DEFAULT_GRADING_SCALE = "0-100"
