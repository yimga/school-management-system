"""Edge purge signal hooks (v4.00.0).

Fires ``services.edge_cache.purge_surrogate_keys`` whenever a tenant-scoped
config row that the runtime endpoints expose is mutated. Best-effort: the
Worker SWR window expires anyway after 5 minutes, so a missed signal is
self-healing.

Hooked in ``apps/api/apps.py::ApiConfig.ready`` via a lazy import. The
``post_save`` handlers are no-op when the model is not importable.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from services.edge_cache import purge_tenant_runtime

logger = logging.getLogger(__name__)


def _tenant_slug(instance) -> str | None:
    school = getattr(instance, "school", None)
    if school is None:
        return None
    return getattr(school, "slug", None) or getattr(school, "subdomain", None)


def _purge(instance, views: tuple[str, ...]) -> None:
    slug = _tenant_slug(instance)
    if not slug:
        return
    try:
        purge_tenant_runtime(slug, views=views)
    except Exception as exc:  # noqa: BLE001 — signal handler must never raise
        logger.debug("edge_cache_signals.purge_failed: %s", exc)


def _register_runtime_defaults() -> None:
    try:
        from apps.platform_runtime.models import RuntimeDefaults  # type: ignore[attr-defined]
    except ImportError:
        return

    @receiver(post_save, sender=RuntimeDefaults, weak=False)
    def _on_runtime_defaults_save(sender, instance, **kwargs):  # noqa: ARG001
        _purge(instance, ("runtime_defaults",))


def _register_site_settings() -> None:
    try:
        from apps.siteconfig.models import SiteSettings  # type: ignore[attr-defined]
    except ImportError:
        return

    @receiver(post_save, sender=SiteSettings, weak=False)
    def _on_site_settings_save(sender, instance, **kwargs):  # noqa: ARG001
        _purge(instance, ("site_settings_snapshot", "feature_flags"))


def register_all() -> None:
    """Idempotent — call from ``ApiConfig.ready``."""
    _register_runtime_defaults()
    _register_site_settings()
