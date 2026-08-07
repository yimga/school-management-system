"""
Platform defaults for site config (B2 — siteconfig singleton holds platform defaults only).
Canonical default values used when no tenant/school override exists.
"""

from __future__ import annotations

import os

# Keys and defaults used by get_effective_* and runtime; avoid reading the site settings singleton in tenant paths.
PLATFORM_DEFAULT_BACKEND_FEATURE_FLAGS: dict[str, object] = {
    "enable_api_schema_ui": True,
    "allowed_roles_api_schema": [],
    "require_guardian_finance_opt_in": False,
}

# The platform-wide floor used only when a tenant has configured nothing. It is a
# NEUTRAL default (per-tenant config is the load-bearing layer — see M2/M3), but
# it is env-overridable so a regionally-focused deployment can shift the floor
# itself (e.g. a francophone-first instance: PLATFORM_DEFAULT_CURRENCY=XAF,
# PLATFORM_DEFAULT_GRADING_SCALE=french_0_20) instead of being pinned to US values.
PLATFORM_DEFAULT_REGION_CODE = os.environ.get("PLATFORM_DEFAULT_REGION_CODE", "GLOBAL")
PLATFORM_DEFAULT_CURRENCY = os.environ.get("PLATFORM_DEFAULT_CURRENCY", "USD")
PLATFORM_DEFAULT_GRADING_SCALE = os.environ.get(
    "PLATFORM_DEFAULT_GRADING_SCALE", "0-100"
)
