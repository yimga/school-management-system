"""Resolve a *usable* OAuth access token for a tenant connector.

Consumers (video meetings, calendar sync, chat) must never read
``ServiceIntegration.config["access_token"]`` raw: once the row encrypts its
secret-named keys at rest, that value is an ``enc::fernet::`` blob, not a
bearer. ``get_valid_access_token`` is the single seam that:

1. finds the tenant's active connection for the connector slug,
2. best-effort refreshes it inline when the persisted token is near expiry
   (the background beat also sweeps every 5 min; this guards the gap when a
   token is used right at expiry or the beat is down), and
3. returns the *decrypted* access token.

It never raises — a resolver/refresh/decrypt hiccup returns ``""`` so the
caller can fall back (e.g. to a serverless Jitsi room) instead of crashing.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_valid_access_token(school, slug: str) -> str:
    """Return a decrypted, refreshed-if-due bearer for ``(school, slug)`` or ``""``."""
    if school is None or not slug:
        return ""
    row = _tenant_connection_row(school, slug)
    if row is not None:
        _refresh_if_due(row, slug)
        token = _decrypted_access_token(row)
        if token:
            return token
    # Fall back to the resolver cascade (parent-school chain / env default),
    # which also decrypts. Covers connections inherited from a parent school.
    try:
        from apps.communication.integrations import _resolve_connector_config_safe

        cfg = _resolve_connector_config_safe(slug, school=school)
        return str((cfg.get("access_token") or "")).strip()
    except Exception:  # noqa: BLE001 — never break the caller on a lookup fault
        logger.warning(
            "get_valid_access_token: cascade fallback failed for %s", slug, exc_info=True
        )
        return ""


def _tenant_connection_row(school, slug):
    try:
        from django.db.models import Q

        from apps.siteconfig.models_platform_catalog import ServiceIntegration

        return (
            ServiceIntegration.objects.filter(
                Q(connector_slug=slug) | Q(service_name=slug),
                school=school,
                is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "get_valid_access_token: row lookup failed for %s", slug, exc_info=True
        )
        return None


def _refresh_if_due(row, slug: str) -> None:
    try:
        from apps.integrations_marketplace.token_refresh import _is_due, refresh_single

        if _is_due(dict(row.config or {})):
            refresh_single(row)
            row.refresh_from_db(fields=["config"])
    except Exception:  # noqa: BLE001 — a refresh hiccup must not break the caller
        logger.warning(
            "get_valid_access_token: refresh-if-due failed for %s", slug, exc_info=True
        )


def _decrypted_access_token(row) -> str:
    try:
        from apps.communication.secret_config import decrypt_config

        return str(
            (decrypt_config(dict(row.config or {})).get("access_token") or "")
        ).strip()
    except Exception:  # noqa: BLE001
        logger.warning("get_valid_access_token: decrypt failed", exc_info=True)
        return ""


__all__ = ["get_valid_access_token"]
