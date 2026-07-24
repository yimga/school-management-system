"""Plugin discovery for Migration Cloud connectors (audit D-5 / D-7).

Core ships a fixed set of connectors (``registry.bootstrap_connectors``). To
make the connector surface *marketplace-extensible* — so an installed partner
package can register a connector WITHOUT a core deploy — this module discovers
additional connectors from two sources at bootstrap:

1. ``settings.MIGRATION_CLOUD_CONNECTOR_PLUGINS`` — a list of dotted import
   paths, each pointing at a :class:`~apps.migration_cloud.connectors.base.ConnectorAdapter`
   subclass, an adapter instance, or a zero-arg factory returning one.
2. Python entry-points group ``runmycampus.migration_connectors`` — any
   installed distribution can advertise a connector here via its packaging
   metadata (``[project.entry-points."runmycampus.migration_connectors"]``).

Every discovered object is validated against the ``ConnectorAdapter`` ABC
before it is handed back for registration. A broken plugin (import error,
wrong type, missing ``profile_key``, or an abstract subclass whose methods are
unimplemented) logs a WARNING and is skipped — a partner's mistake never
crashes bootstrap or takes down the built-in connectors.
"""

from __future__ import annotations

import logging
from typing import Any

from .base import ConnectorAdapter

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "runmycampus.migration_connectors"
SETTINGS_KEY = "MIGRATION_CLOUD_CONNECTOR_PLUGINS"


def validate_connector(candidate: Any) -> ConnectorAdapter:
    """Coerce + validate a discovered object into a ``ConnectorAdapter`` instance.

    Accepts an adapter instance, a ``ConnectorAdapter`` subclass, or a zero-arg
    factory returning one. Raises ``TypeError`` / ``ValueError`` on anything
    that is not a usable connector — abstract subclasses raise ``TypeError`` at
    instantiation because their abstract methods are unimplemented.
    """
    obj = candidate
    if isinstance(obj, type):
        if not issubclass(obj, ConnectorAdapter):
            raise TypeError(f"{obj!r} is not a ConnectorAdapter subclass")
        obj = obj()  # abstract subclasses raise TypeError here
    elif not isinstance(obj, ConnectorAdapter) and callable(obj):
        obj = obj()  # zero-arg factory

    if not isinstance(obj, ConnectorAdapter):
        raise TypeError(f"{candidate!r} did not resolve to a ConnectorAdapter")

    profile_key = getattr(obj, "profile_key", "")
    if not isinstance(profile_key, str) or not profile_key.strip():
        raise ValueError(f"{obj!r} has an empty profile_key")
    return obj


def _load_from_settings() -> list[ConnectorAdapter]:
    from django.conf import settings
    from django.utils.module_loading import import_string

    adapters: list[ConnectorAdapter] = []
    paths = getattr(settings, SETTINGS_KEY, None) or []
    if isinstance(paths, str):
        paths = [paths]
    for dotted in paths:
        try:
            target = import_string(dotted)
            adapter = validate_connector(target)
        except Exception as exc:  # noqa: BLE001 — a broken plugin must never crash bootstrap
            logger.warning(
                "migration_cloud.connectors: skipping settings plugin %r (%s)",
                dotted,
                type(exc).__name__,
            )
            continue
        adapters.append(adapter)
    return adapters


def _load_from_entry_points() -> list[ConnectorAdapter]:
    adapters: list[ConnectorAdapter] = []
    try:
        from importlib import metadata as importlib_metadata
    except ImportError:  # pragma: no cover — importlib.metadata is stdlib on >=3.8
        return adapters

    try:
        all_entry_points = importlib_metadata.entry_points()
        # Python 3.10+ exposes the selectable ``EntryPoints`` API; older
        # versions return a plain ``{group: [EntryPoint, ...]}`` dict.
        if hasattr(all_entry_points, "select"):
            group = all_entry_points.select(group=ENTRY_POINT_GROUP)
        else:  # pragma: no cover — Python <3.10
            group = all_entry_points.get(ENTRY_POINT_GROUP, [])
    except Exception as exc:  # noqa: BLE001 — metadata discovery is best-effort
        logger.warning(
            "migration_cloud.connectors: entry-point discovery unavailable (%s)",
            type(exc).__name__,
        )
        return adapters

    for entry in group:
        try:
            target = entry.load()
            adapter = validate_connector(target)
        except Exception as exc:  # noqa: BLE001 — a broken plugin must never crash bootstrap
            logger.warning(
                "migration_cloud.connectors: skipping entry-point plugin %r (%s)",
                getattr(entry, "name", "?"),
                type(exc).__name__,
            )
            continue
        adapters.append(adapter)
    return adapters


def load_plugin_connectors() -> list[ConnectorAdapter]:
    """Discover every plugin connector (settings + entry-points), validated.

    Never raises — each source isolates its own failures and skips broken
    plugins with a WARNING, so the caller can register the result unconditionally.
    """
    adapters: list[ConnectorAdapter] = []
    adapters.extend(_load_from_settings())
    adapters.extend(_load_from_entry_points())
    return adapters
