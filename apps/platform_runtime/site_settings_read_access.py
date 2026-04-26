"""
Approved platform SiteSettings read / persist entry points (SOT 1035+).

**Do not** import ``SiteSettings`` from ``apps.siteconfig.models`` in product code outside
``siteconfig/models.py`` and ``platform_runtime/helpers.py``. Use the callables re-exported
here or the same symbols from :mod:`apps.platform_runtime.helpers` (single runtime access layer).
"""

from __future__ import annotations

from apps.platform_runtime.helpers import (
    get_effective_flags,
    get_effective_marketplace_integration_settings,
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
    persist_platform_runtime_payload_updates,
)

__all__ = [
    "get_effective_flags",
    "get_effective_marketplace_integration_settings",
    "get_effective_site_settings",
    "get_platform_site_settings_record",
    "invalidate_effective_site_settings_cache",
    "persist_platform_runtime_payload_updates",
]
