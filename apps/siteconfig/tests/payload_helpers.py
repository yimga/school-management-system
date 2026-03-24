"""Phase B test helpers: behavioral SiteSettings keys live in RuntimeDefaults.payload."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.helpers import invalidate_effective_site_settings_cache
from apps.siteconfig.models import SiteSettings


def persist_runtime_site_settings_payload(**kwargs: Any) -> None:
    """Merge JSON-safe keys into platform RuntimeDefaults (same path as production)."""
    SiteSettings._persist_runtime_payload_updates(kwargs)
    invalidate_effective_site_settings_cache()
