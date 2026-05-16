"""
Connector cascade resolver.

Picks the right `ServiceIntegration` row for a (connector_slug, school, campus)
tuple by walking the 4-step cascade defined in the platform's no-hardcoding
contract:

  1. Per-campus row      (school=X, campus=Y, connector_slug=Z, is_active=True)
  2. Per-school row      (school=X, campus=NULL, connector_slug=Z, is_active=True)
  3. Per-parent-school   (walk School.parent_school chain, repeat step 2 at each
                           ancestor — supports multi-school district / group rollups)
  4. Platform env default (INTEGRATIONS_<UPPER_SLUG>_DEFAULT_CONFIG, JSON-encoded;
                            primarily for development and the "platform-owns-the-
                            credentials" scenario, e.g. shared Zoom marketplace
                            app where every tenant uses the platform's app id but
                            their own per-user tokens)

The cascade returns a `ResolvedConnector` dataclass — never the raw model
row — so call sites get a stable contract that survives schema renames.

Multi-school / multi-campus semantics:
- A *tenant* in this codebase is a `School` row. Multi-school tenants use the
  `parent_school` FK chain (`School.hierarchy_path`). The resolver walks that
  chain so a parent district can configure Zoom once and all child schools
  inherit unless they override.
- A *campus* is a `schoolops.Campus` row scoped to one School. Per-campus rows
  let a multi-campus school point each campus's "default video room" at a
  different Zoom sub-account if needed; absence of a campus row is the common
  case and falls through to school-level.

All queries are tenant-isolated via the `school=` kwarg on every `.filter` —
no `# tenant-isolation-allow` annotations needed.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from apps.integrations_marketplace.connector_registry import (
    Connector,
    get_connector,
)
from apps.siteconfig.models_platform_catalog import ServiceIntegration

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedConnector:
    """A connector resolved against the (school, campus) scope cascade."""

    connector: Connector
    source: str  # "campus" | "school" | "parent_school:<id>" | "env_default" | "none"
    integration_id: int | None
    config: dict[str, Any]
    scopes: list[str]
    is_active: bool

    @property
    def is_configured(self) -> bool:
        return self.source != "none"

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


def _row_to_resolved(
    *, connector: Connector, row: ServiceIntegration, source: str
) -> ResolvedConnector:
    return ResolvedConnector(
        connector=connector,
        source=source,
        integration_id=row.pk,
        config=dict(row.config or {}),
        scopes=list(row.enabled_scopes or []),
        is_active=bool(row.is_active),
    )


def _row_for_scope(
    *, school, campus, connector_slug: str
) -> ServiceIntegration | None:
    """Active row at the exact (school, campus) scope. campus may be None."""
    qs = ServiceIntegration.objects.filter(
        school=school,
        connector_slug__iexact=connector_slug,
        is_active=True,
    )
    if campus is None:
        qs = qs.filter(campus__isnull=True)
    else:
        qs = qs.filter(campus=campus)
    return qs.order_by("-updated_at", "-id").first()


def _env_default(*, connector_slug: str) -> dict[str, Any] | None:
    """Read platform-level default config from env, if any."""
    key = f"INTEGRATIONS_{connector_slug.upper()}_DEFAULT_CONFIG"
    raw = os.getenv(key, "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(
            "Connector env default for %s is not valid JSON; ignoring.", connector_slug
        )
        return None
    if not isinstance(parsed, dict):
        logger.warning(
            "Connector env default for %s must be a JSON object; got %s.",
            connector_slug,
            type(parsed).__name__,
        )
        return None
    return parsed


def resolve_connector_config(
    connector_slug: str,
    *,
    school=None,
    campus=None,
) -> ResolvedConnector | None:
    """
    Resolve `connector_slug` for the given (school, campus) scope.

    Returns `None` when the slug is not in the registry. Returns a
    `ResolvedConnector` with `source="none"` when the slug is valid but
    no scope-cascade level produced a row (callers can render a "Connect …"
    CTA in that case).
    """
    connector = get_connector(connector_slug)
    if connector is None:
        return None
    slug = connector.slug

    if school is None:
        # Platform-default fallback only — no per-tenant scope to walk.
        env_cfg = _env_default(connector_slug=slug)
        if env_cfg is not None:
            return ResolvedConnector(
                connector=connector,
                source="env_default",
                integration_id=None,
                config=env_cfg,
                scopes=list(connector.default_scopes),
                is_active=True,
            )
        return ResolvedConnector(
            connector=connector,
            source="none",
            integration_id=None,
            config={},
            scopes=list(connector.default_scopes),
            is_active=False,
        )

    # 1. Per-campus override
    if campus is not None:
        row = _row_for_scope(school=school, campus=campus, connector_slug=slug)
        if row:
            return _row_to_resolved(connector=connector, row=row, source="campus")

    # 2. Per-school row (campus IS NULL)
    row = _row_for_scope(school=school, campus=None, connector_slug=slug)
    if row:
        return _row_to_resolved(connector=connector, row=row, source="school")

    # 3. Walk parent_school chain for district / group rollups.
    visited: set[int] = {school.pk}
    current = getattr(school, "parent_school", None)
    while current is not None and current.pk not in visited:
        visited.add(current.pk)
        row = _row_for_scope(school=current, campus=None, connector_slug=slug)
        if row:
            return _row_to_resolved(
                connector=connector, row=row, source=f"parent_school:{current.pk}"
            )
        current = getattr(current, "parent_school", None)

    # 4. Platform env default.
    env_cfg = _env_default(connector_slug=slug)
    if env_cfg is not None:
        return ResolvedConnector(
            connector=connector,
            source="env_default",
            integration_id=None,
            config=env_cfg,
            scopes=list(connector.default_scopes),
            is_active=True,
        )

    return ResolvedConnector(
        connector=connector,
        source="none",
        integration_id=None,
        config={},
        scopes=list(connector.default_scopes),
        is_active=False,
    )


def list_connections_for_school(school) -> list[dict[str, Any]]:
    """
    Hub UI helper: returns one dict per registry connector with its current
    resolution status for the school (school-level only — campus overrides
    are surfaced by a separate per-campus view).
    """
    from apps.integrations_marketplace.connector_registry import list_connectors

    out: list[dict[str, Any]] = []
    for connector in list_connectors():
        resolved = resolve_connector_config(connector.slug, school=school)
        out.append(
            {
                "connector": connector.to_dict(),
                "source": resolved.source if resolved else "none",
                "is_configured": bool(resolved and resolved.is_configured),
                "is_active": bool(resolved and resolved.is_active),
                "integration_id": resolved.integration_id if resolved else None,
            }
        )
    return out


__all__ = [
    "ResolvedConnector",
    "resolve_connector_config",
    "list_connections_for_school",
]
