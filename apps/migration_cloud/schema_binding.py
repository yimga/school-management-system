"""Resolve the PostgreSQL tenant schema for a School.

Migration Cloud historically used ``getattr(school, "schema_name", "")``.
``School`` has no such attribute — the live schema lives on
``customers.Client.schema_name`` (typically ``s_<uuid-hex>``). Empty
``MigrationBundle.schema_name`` causes ``apply_bundle`` to skip
``schema_context``, so landed rows never appear in the tenant school UI.

This module is the single resolver for intake, bind, companion, and apply.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def resolve_school_schema_name(school: Any) -> str:
    """Return the tenant schema name for ``school``, or ``""`` if unbound.

    Resolution order:
    1. ``apps.schools.tenant_offboarding.get_schema_name`` (Client FK lookup)
    2. Direct ``Client.objects.filter(school=...).schema_name``
    3. ``apps.schools.domain_sync._schema_name_for_school`` as last-resort
       deterministic name (matches provisioned schema convention)
    """
    if school is None or getattr(school, "pk", None) is None:
        return ""

    try:
        from apps.schools.tenant_offboarding import get_schema_name

        resolved = get_schema_name(school)
        if resolved:
            return str(resolved).strip()
    except Exception:  # noqa: BLE001 — soft: never break intake on helper import
        logger.debug("mc.schema_binding: get_schema_name failed", exc_info=True)

    try:
        from apps.customers.models import Client

        client = Client.objects.filter(school_id=school.pk).only("schema_name").first()
        if client and getattr(client, "schema_name", None):
            return str(client.schema_name).strip()
    except Exception:  # noqa: BLE001
        logger.debug("mc.schema_binding: Client lookup failed", exc_info=True)

    try:
        from apps.schools.domain_sync import _schema_name_for_school

        return str(_schema_name_for_school(school) or "").strip()
    except Exception:  # noqa: BLE001
        logger.debug("mc.schema_binding: _schema_name_for_school failed", exc_info=True)
        return ""


def ensure_bundle_schema_name(bundle) -> str:
    """Fill ``bundle.schema_name`` from its school when empty; persist if changed.

    Returns the effective schema name (may still be empty for unbound bundles).
    """
    current = (getattr(bundle, "schema_name", None) or "").strip()
    if current:
        return current
    school = getattr(bundle, "school", None)
    if school is None and getattr(bundle, "school_id", None):
        try:
            from apps.schools.models import School

            school = School.objects.filter(pk=bundle.school_id).first()
        except Exception:  # noqa: BLE001
            school = None
    resolved = resolve_school_schema_name(school)
    if resolved and resolved != (bundle.schema_name or ""):
        bundle.schema_name = resolved
        try:
            bundle.save(update_fields=["schema_name", "updated_at"])
        except Exception:  # noqa: BLE001 — caller may hold unsaved instance
            bundle.schema_name = resolved
    return (bundle.schema_name or "").strip()
